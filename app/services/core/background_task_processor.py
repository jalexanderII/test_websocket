import asyncio
import inspect
import json
import uuid
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any, Callable, TypedDict, cast

from pydantic import BaseModel
from redis.asyncio.client import PubSub

from app.config.logger import get_logger
from app.config.redis import async_redis
from app.utils.async_redis_utils.dict import AsyncDict
from app.utils.async_redis_utils.set import AsyncSet
from app.utils.async_redis_utils.task_serializer import SerializableTask
from app.utils.universal_serializer import safe_json_dumps

logger = get_logger(__name__)


class TaskData(TypedDict):
    """Type definition for task data stored in Redis"""

    status: str
    created_at: str  # ISO format datetime string
    updated_at: str  # ISO format datetime string
    completed_at: str | None  # ISO format datetime string
    result: Any | None
    error: str | None


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TASK_KEY_PREFIX = "background_task_results:"
TASK_CHANNEL_PREFIX = "task_updates:"


class BackgroundTaskProcessor:
    def __init__(self, max_workers: int = 10, result_ttl: int = 3600):
        """
        Initialize the background task processor

        Args:
            max_workers: Maximum number of concurrent worker threads
            result_ttl: Time in seconds to keep completed task results
        """
        self._redis = async_redis.client
        self._max_workers = max_workers
        self._result_ttl = result_ttl
        self._semaphore = asyncio.Semaphore(max_workers)
        self._background_tasks: AsyncSet[SerializableTask] = AsyncSet(
            "background_tasks", connection_manager=async_redis
        )
        self._tasks: AsyncDict[str, SerializableTask] = AsyncDict("tasks", connection_manager=async_redis)
        self._task_to_id: AsyncDict[SerializableTask, str] = AsyncDict("task_to_id", connection_manager=async_redis)

        # Register our custom type with the serializers
        self._background_tasks.register_types(SerializableTask)
        self._tasks.register_types(SerializableTask)
        self._task_to_id.register_types(SerializableTask)

    async def _remove_task_from_set(self, task: asyncio.Task) -> None:
        """Remove a task from the background tasks set and tasks mapping"""
        serializable_task = SerializableTask(task)
        await self._background_tasks.remove(serializable_task)
        if task_id := await self._task_to_id.get(serializable_task):
            await self._tasks.delete(task_id)
            await self._task_to_id.delete(serializable_task)
            logger.debug("Removed task %s from tasks mapping", task_id)

    def _serialize_result(self, result: Any) -> dict[str, Any]:
        if isinstance(result, BaseModel):
            return result.model_dump()
        return json.loads(safe_json_dumps(result))

    def _get_task_key(self, task_id: str) -> str:
        """Get the Redis key for a task"""
        return f"{TASK_KEY_PREFIX}{task_id}"

    def _get_task_channel(self, task_id: str) -> str:
        """Get the Redis channel name for a task"""
        return f"{TASK_CHANNEL_PREFIX}{task_id}"

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

        # Store initial task metadata with RUNNING state since tasks start immediately
        task_data = {
            "status": TaskStatus.RUNNING,  # Tasks start in RUNNING state
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

        # Create and start task immediately
        if is_async:
            coro = self._execute_async_task(task_id, func, *args, **kwargs)
        else:
            coro = self._execute_sync_task(task_id, func, *args, **kwargs)

        # Create and store task
        task = asyncio.create_task(coro, name=task_id)
        serializable_task = SerializableTask(task)

        # Store task references
        await self._background_tasks.add(serializable_task)
        await self._tasks.set(task_id, serializable_task)
        await self._task_to_id.set(serializable_task, task_id)

        # Setup cleanup callback
        task.add_done_callback(lambda t: asyncio.create_task(self._remove_task_from_set(t)))

        return task_id

    async def _start_task(self, task_id: str) -> None:
        """Start task execution after a short delay to allow status checks"""
        await asyncio.sleep(0.1)  # Small delay to allow status checks
        if serializable_task := await self._tasks.get(task_id):
            if task := serializable_task.get_task():
                if not task.done() and not task.cancelled():
                    await self._update_task_status(task_id, TaskStatus.RUNNING)

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
            if serializable_task := await self._tasks.get(task_id):
                logger.debug("Found active task for %s, cancelling it", task_id)
                if task := serializable_task.get_task():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    await self._update_task_status(task_id, TaskStatus.CANCELLED)
                    return True
        return False

    async def cleanup_old_tasks(self, max_age: timedelta | None = None) -> int:
        """
        Clean up completed/failed/cancelled tasks older than max_age
        Returns number of tasks cleaned up
        """
        max_age = max_age if max_age is not None else timedelta(seconds=self._result_ttl)
        cleaned = 0

        # Get all task keys
        pattern = f"{TASK_KEY_PREFIX}*"
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
