import asyncio
import inspect
import json
import uuid
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any, Callable, Optional, TypedDict, cast

from redis_data_structures import Dict as RedisDict

from app.config.redis_config import redis_manager


class TaskData(TypedDict):
    """Type definition for task data stored in Redis"""

    status: str
    created_at: str  # ISO format datetime string
    updated_at: str  # ISO format datetime string
    completed_at: str | None  # ISO format datetime string
    result: Any | None
    error: str | None


def _serialize_datetime(obj: Any) -> Any:
    """Helper function to serialize datetime objects for JSON"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundTaskProcessor:
    def __init__(self, max_workers: int = 10, result_ttl: int = 3600):
        """
        Initialize the background task processor

        Args:
            max_workers: Maximum number of concurrent worker threads
            result_ttl: Time in seconds to keep completed task results
        """
        self._task_results: RedisDict[str, TaskData] = RedisDict(
            "background_task_results", connection_manager=redis_manager
        )
        self._max_workers = max_workers
        self._result_ttl = result_ttl
        self._semaphore = asyncio.Semaphore(max_workers)
        self._background_tasks: set[asyncio.Task] = set()

    def _remove_task_from_set(self, task: asyncio.Task) -> None:
        """Remove a task from the background tasks set"""
        self._background_tasks.discard(task)

    def _serialize_result(self, result: Any) -> Any:
        """Serialize result for storage, handling special types like datetime"""
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return json.loads(json.dumps(result, default=_serialize_datetime))

    async def add_task(self, func: Callable, *args, task_id: Optional[str] = None, **kwargs) -> str:
        """
        Add a task to be executed in the background

        Args:
            func: The function to execute
            *args: Positional arguments for the function
            task_id: Optional task ID. If not provided, one will be generated
            **kwargs: Keyword arguments for the function

        Returns:
            task_id: The ID of the scheduled task
        """
        task_id = task_id or str(uuid.uuid4())

        # Store initial task metadata
        self._task_results[task_id] = {
            "status": TaskStatus.PENDING,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": None,
        }

        # Check if function is already async
        is_async = inspect.iscoroutinefunction(func)

        # Create and store task
        if is_async:
            task = asyncio.create_task(self._execute_async_task(task_id, func, *args, **kwargs))
        else:
            task = asyncio.create_task(self._execute_sync_task(task_id, func, *args, **kwargs))

        # Add task to set and setup cleanup
        self._background_tasks.add(task)
        task.add_done_callback(self._remove_task_from_set)

        return task_id

    async def _execute_async_task(self, task_id: str, func: Callable, *args, **kwargs) -> None:
        """Execute an async task directly"""
        async with self._semaphore:
            try:
                self._update_task_status(task_id, TaskStatus.RUNNING)
                result = await func(*args, **kwargs)
                self._store_task_result(task_id, result)
            except Exception as e:
                self._store_task_error(task_id, str(e))

    async def _execute_sync_task(self, task_id: str, func: Callable, *args, **kwargs) -> None:
        """Execute a sync task in the thread pool"""
        async with self._semaphore:
            try:
                self._update_task_status(task_id, TaskStatus.RUNNING)
                # Run sync function in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, partial(func, *args, **kwargs))
                self._store_task_result(task_id, result)
            except Exception as e:
                self._store_task_error(task_id, str(e))

    def _update_task_status(self, task_id: str, status: str) -> None:
        """Update the status of a task"""
        if task_data := self._task_results.get(task_id):
            task_data["status"] = status
            task_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._task_results[task_id] = task_data

    def _store_task_result(self, task_id: str, result: Any) -> None:
        """Store the result of a completed task"""
        if task_data := self._task_results.get(task_id):
            task_data.update(
                {
                    "status": TaskStatus.COMPLETED,
                    "result": self._serialize_result(result),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            self._task_results[task_id] = task_data

    def _store_task_error(self, task_id: str, error: str) -> None:
        """Store error information for a failed task"""
        if task_data := self._task_results.get(task_id):
            task_data.update(
                {
                    "status": TaskStatus.FAILED,
                    "error": error,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            self._task_results[task_id] = task_data

    async def get_task_result(self, task_id: str) -> Optional[TaskData]:
        """Get the current status and result of a task"""
        if result := self._task_results.get(task_id):
            return cast(TaskData, result)
        return None

    async def cancel_task(self, task_id: str) -> bool:
        """
        Attempt to cancel a running task
        Returns True if task was cancelled, False if task couldn't be cancelled
        """
        if task_data := self._task_results.get(task_id):
            if task_data["status"] in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                task_data.update(
                    {
                        "status": TaskStatus.CANCELLED,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                self._task_results[task_id] = task_data
                return True
        return False

    async def cleanup_old_tasks(self, max_age: Optional[timedelta] = None) -> int:
        """
        Clean up completed/failed tasks older than max_age
        Returns number of tasks cleaned up
        """
        max_age = max_age if max_age is not None else timedelta(seconds=self._result_ttl)
        cleaned = 0

        for task_id in self._task_results.keys():
            if task_data := self._task_results.get(task_id):
                completed_at = task_data.get("completed_at")
                if completed_at is None:
                    continue

                completed_dt = datetime.fromisoformat(completed_at)
                if (
                    task_data["status"] in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
                    and datetime.now(timezone.utc) - completed_dt > max_age
                ):
                    del self._task_results[task_id]
                    cleaned += 1

        return cleaned
