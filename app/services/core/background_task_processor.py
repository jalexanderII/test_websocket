import asyncio
import inspect
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any, Callable, TypedDict, cast

from redis.asyncio.client import PubSub

from app.config.redis import async_redis
from app.utils.universal_serializer import safe_json_dumps

logger = logging.getLogger(__name__)


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
        self._redis = async_redis  # Use async Redis instead of sync
        self._task_key_prefix = "background_task_results:"
        self._task_channel_prefix = "task_updates:"
        self._max_workers = max_workers
        self._result_ttl = result_ttl
        self._semaphore = asyncio.Semaphore(max_workers)
        self._background_tasks: set[asyncio.Task] = set()
        self._tasks: dict[str, asyncio.Task] = {}  # Mapping of task_id to asyncio.Task

    def _remove_task_from_set(self, task: asyncio.Task) -> None:
        """Remove a task from the background tasks set and tasks mapping"""
        self._background_tasks.discard(task)
        # Find and remove the task from the tasks mapping
        task_ids_to_remove = [task_id for task_id, t in self._tasks.items() if t == task]
        for task_id in task_ids_to_remove:
            self._tasks.pop(task_id, None)
            logger.debug("Removed task %s from tasks mapping", task_id)

    def _serialize_result(self, result: Any) -> Any:
        """Serialize result for storage, handling special types like datetime"""
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return json.loads(safe_json_dumps(result, default=_serialize_datetime))

    def _get_task_key(self, task_id: str) -> str:
        """Get the Redis key for a task"""
        return f"{self._task_key_prefix}{task_id}"

    def _get_task_channel(self, task_id: str) -> str:
        """Get the Redis channel name for a task"""
        return f"{self._task_channel_prefix}{task_id}"

    async def _publish_task_update(self, task_id: str, status: str, data: dict | None = None) -> None:
        """Publish task updates to Redis channel"""
        channel = self._get_task_channel(task_id)
        message = {"task_id": task_id, "status": status, "data": data or {}, "timestamp": datetime.now(UTC).isoformat()}
        await self._redis.publish(channel, safe_json_dumps(message))

    async def subscribe_to_task_updates(self, task_id: str) -> PubSub:
        """Subscribe to task updates and return the pubsub connection"""
        pubsub = self._redis.pubsub()
        channel = self._get_task_channel(task_id)
        await pubsub.subscribe(channel)
        return pubsub

    async def add_task(self, func: Callable, *args, task_id: str | None = None, **kwargs) -> str:
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
        logger.info("Adding new task with ID: %s", task_id)

        # Store initial task metadata
        task_data = {
            "status": TaskStatus.PENDING,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
            "result": None,
            "error": None,
        }
        await self._redis.set(self._get_task_key(task_id), safe_json_dumps(task_data), ex=self._result_ttl)

        # Check if function is already async
        is_async = inspect.iscoroutinefunction(func)
        logger.debug("Task %s is %s", task_id, "async" if is_async else "sync")

        # Create and store task
        if is_async:
            task = asyncio.create_task(self._execute_async_task(task_id, func, *args, **kwargs))
        else:
            task = asyncio.create_task(self._execute_sync_task(task_id, func, *args, **kwargs))

        # Add task to set and setup cleanup
        self._background_tasks.add(task)
        self._tasks[task_id] = task  # Store in tasks mapping
        task.add_done_callback(self._remove_task_from_set)

        return task_id

    async def _execute_async_task(self, task_id: str, func: Callable, *args, **kwargs) -> None:
        """Execute an async task directly"""
        logger.debug("Starting execution of async task %s", task_id)
        async with self._semaphore:
            try:
                await self._update_task_status(task_id, TaskStatus.RUNNING)
                result = await func(*args, **kwargs)
                current_task = asyncio.current_task()
                if current_task and current_task.cancelled():
                    logger.info("Task %s was cancelled during execution", task_id)
                    await self._update_task_status(task_id, TaskStatus.CANCELLED)
                    return
                await self._store_task_result(task_id, result)
                await self._update_task_status(task_id, TaskStatus.COMPLETED)
                logger.info("Successfully completed async task %s", task_id)
            except asyncio.CancelledError:
                logger.info("Task %s was cancelled", task_id)
                await self._update_task_status(task_id, TaskStatus.CANCELLED)
            except Exception as e:
                error_msg = str(e)
                logger.error("Error executing async task %s: %s", task_id, error_msg)
                if "Event loop is closed" in error_msg:
                    return
                await self._store_task_error(task_id, error_msg)
                await self._update_task_status(task_id, TaskStatus.FAILED)

    async def _execute_sync_task(self, task_id: str, func: Callable, *args, **kwargs) -> None:
        """Execute a sync task in the thread pool"""
        logger.debug("Starting execution of sync task %s", task_id)
        async with self._semaphore:
            try:
                await self._update_task_status(task_id, TaskStatus.RUNNING)
                # Run sync function in thread pool
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, partial(func, *args, **kwargs))
                current_task = asyncio.current_task()
                if current_task and current_task.cancelled():
                    logger.info("Task %s was cancelled during execution", task_id)
                    await self._update_task_status(task_id, TaskStatus.CANCELLED)
                    return
                await self._store_task_result(task_id, result)
                await self._update_task_status(task_id, TaskStatus.COMPLETED)
                logger.info("Successfully completed sync task %s", task_id)
            except asyncio.CancelledError:
                logger.info("Task %s was cancelled", task_id)
                await self._update_task_status(task_id, TaskStatus.CANCELLED)
            except Exception as e:
                error_msg = str(e)
                logger.error("Error executing sync task %s: %s", task_id, error_msg)
                if "Event loop is closed" in error_msg:
                    return
                await self._store_task_error(task_id, error_msg)
                await self._update_task_status(task_id, TaskStatus.FAILED)

    async def _update_task_status(self, task_id: str, status: str) -> None:
        """Update the status of a task"""
        task_key = self._get_task_key(task_id)
        if task_data_str := await self._redis.get(task_key):
            task_data = json.loads(task_data_str)
            task_data["status"] = status
            task_data["updated_at"] = datetime.now(UTC).isoformat()
            await self._redis.set(task_key, safe_json_dumps(task_data), ex=self._result_ttl)
            # Also publish status update
            await self._publish_task_update(task_id, status)

    async def _store_task_result(self, task_id: str, result: Any) -> None:
        """Store the result of a completed task and publish update"""
        task_key = self._get_task_key(task_id)
        if task_data_str := await self._redis.get(task_key):
            task_data = json.loads(task_data_str)
            task_data.update(
                {
                    "status": TaskStatus.COMPLETED,
                    "result": self._serialize_result(result),
                    "updated_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            )
            await self._redis.set(task_key, safe_json_dumps(task_data), ex=self._result_ttl)

            # Publish update
            await self._publish_task_update(task_id, TaskStatus.COMPLETED, {"result": self._serialize_result(result)})

    async def _store_task_error(self, task_id: str, error: str) -> None:
        """Store error information for a failed task and publish update"""
        task_key = self._get_task_key(task_id)
        if task_data_str := await self._redis.get(task_key):
            task_data = json.loads(task_data_str)
            task_data.update(
                {
                    "status": TaskStatus.FAILED,
                    "error": error,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            )
            await self._redis.set(task_key, safe_json_dumps(task_data), ex=self._result_ttl)

            # Publish update
            await self._publish_task_update(task_id, TaskStatus.FAILED, {"error": error})

    async def get_task_result(self, task_id: str) -> TaskData | None:
        """Get the current status and result of a task"""
        task_key = self._get_task_key(task_id)
        if result := await self._redis.get(task_key):
            return cast(TaskData, json.loads(result))
        return None

    async def cancel_task(self, task_id: str) -> bool:
        """
        Attempt to cancel a running task
        Returns True if task was cancelled, False if task couldn't be cancelled
        """
        logger.info("Attempting to cancel task %s", task_id)
        task_key = self._get_task_key(task_id)
        if task_data_str := await self._redis.get(task_key):
            task_data = json.loads(task_data_str)
            # Only allow cancelling pending or running tasks
            if task_data["status"] not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                logger.debug("Cannot cancel task %s in status %s", task_id, task_data["status"])
                return False

            # Cancel the actual asyncio task if it exists
            if task := self._tasks.get(task_id):
                logger.debug("Found active task for %s, cancelling it", task_id)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            task_data.update(
                {
                    "status": TaskStatus.CANCELLED,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            )
            await self._redis.set(task_key, safe_json_dumps(task_data), ex=self._result_ttl)
            await self._publish_task_update(task_id, TaskStatus.CANCELLED)
            logger.info("Successfully cancelled task %s", task_id)
            return True

        logger.debug("Task %s not found", task_id)
        return False

    async def cleanup_old_tasks(self, max_age: timedelta | None = None) -> int:
        """
        Clean up completed/failed/cancelled tasks older than max_age
        Returns number of tasks cleaned up
        """
        max_age = max_age if max_age is not None else timedelta(seconds=self._result_ttl)
        cleaned = 0

        # Get all task keys
        pattern = f"{self._task_key_prefix}*"
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern)
            if not keys:
                if cursor == 0:
                    break
                continue

            # Get all task data at once
            task_data_list = await self._redis.mget(keys)
            keys_to_delete = []

            for key, task_data_str in zip(keys, task_data_list, strict=False):
                if not task_data_str:
                    continue

                task_data = json.loads(task_data_str)
                completed_at = task_data.get("completed_at")
                if completed_at is None:
                    continue

                completed_dt = datetime.fromisoformat(completed_at)
                age = datetime.now(UTC) - completed_dt

                if (
                    task_data["status"] in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
                    and age > max_age
                ):
                    keys_to_delete.append(key)

            # Delete keys in batches
            if keys_to_delete:
                await self._redis.delete(*keys_to_delete)
                cleaned += len(keys_to_delete)

            if cursor == 0:
                break

        return cleaned
