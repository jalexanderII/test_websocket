import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator, cast

import pytest
import pytest_asyncio

from app.services.core.background_task_processor import TASK_KEY_PREFIX, BackgroundTaskProcessor, TaskData, TaskStatus


@pytest_asyncio.fixture
async def task_processor() -> AsyncGenerator[BackgroundTaskProcessor, None]:
    """Get task processor for testing."""
    processor = BackgroundTaskProcessor(max_workers=2)
    try:
        yield processor
    finally:
        # Clean up any remaining tasks
        tasks = await processor._background_tasks.members()
        if tasks:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*[task.get_coro() for task in tasks if not task.done()], return_exceptions=True)

        # Clean up Redis keys
        pattern = f"{TASK_KEY_PREFIX}*"
        cursor = 0
        while True:
            cursor, keys = await processor._redis.scan(cursor, match=pattern)
            if keys:
                await processor._redis.delete(*keys)
            if cursor == 0:
                break

        # Close Redis connection using aclose() instead of close()
        await processor._redis.aclose()


async def async_test_func(*args, **kwargs):
    """Test async function that returns its arguments"""
    return {"args": args, "kwargs": kwargs}


def sync_test_func(*args, **kwargs):
    """Test sync function that returns its arguments"""
    return {"args": args, "kwargs": kwargs}


def failing_sync_func():
    """Test function that raises an exception"""
    raise ValueError("Test error")


async def failing_async_func():
    """Test async function that raises an exception"""
    raise ValueError("Test error")


@pytest.mark.asyncio
async def test_add_task_sync(task_processor: BackgroundTaskProcessor):
    """Test adding a synchronous task"""
    task_id = await task_processor.add_task(sync_test_func, 1, 2, kwarg1="test")

    # Check initial task state
    task_data = await task_processor.get_task_result(task_id)
    assert task_data is not None
    assert task_data["status"] == TaskStatus.RUNNING
    assert task_data["result"] is None
    assert task_data["error"] is None
    assert "created_at" in task_data
    assert "updated_at" in task_data


@pytest.mark.asyncio
async def test_add_task_async(task_processor: BackgroundTaskProcessor):
    """Test adding an asynchronous task"""
    task_id = await task_processor.add_task(async_test_func, 1, 2, kwarg1="test")

    # Check initial task state
    task_data = await task_processor.get_task_result(task_id)
    assert task_data is not None
    assert task_data["status"] == TaskStatus.RUNNING
    assert task_data["result"] is None
    assert task_data["error"] is None


@pytest.mark.asyncio
async def test_execute_sync_task(task_processor: BackgroundTaskProcessor):
    """Test executing a synchronous task"""
    task_id = await task_processor.add_task(sync_test_func, 1, 2, kwarg1="test")
    await task_processor._execute_sync_task(task_id, sync_test_func, 1, 2, kwarg1="test")

    task_data = await task_processor.get_task_result(task_id)
    assert task_data is not None
    task_data = cast(TaskData, task_data)
    assert task_data["status"] == TaskStatus.COMPLETED
    assert task_data["result"] == {"args": [1, 2], "kwargs": {"kwarg1": "test"}}
    assert task_data["error"] is None


@pytest.mark.asyncio
async def test_execute_async_task(task_processor: BackgroundTaskProcessor):
    """Test executing an asynchronous task"""
    task_id = await task_processor.add_task(async_test_func, 1, 2, kwarg1="test")
    await task_processor._execute_async_task(task_id, async_test_func, 1, 2, kwarg1="test")

    task_data = await task_processor.get_task_result(task_id)
    assert task_data is not None
    task_data = cast(TaskData, task_data)
    assert task_data["status"] == TaskStatus.COMPLETED
    assert task_data["result"] == {"args": [1, 2], "kwargs": {"kwarg1": "test"}}


@pytest.mark.asyncio
async def test_failing_sync_task(task_processor: BackgroundTaskProcessor):
    """Test handling a failing synchronous task"""
    task_id = await task_processor.add_task(failing_sync_func)
    await task_processor._execute_sync_task(task_id, failing_sync_func)

    task_data = await task_processor.get_task_result(task_id)
    assert task_data is not None
    task_data = cast(TaskData, task_data)
    assert task_data["status"] == TaskStatus.FAILED
    assert task_data["result"] is None
    assert task_data["error"] == "Test error"


@pytest.mark.asyncio
async def test_failing_async_task(task_processor: BackgroundTaskProcessor):
    """Test handling a failing asynchronous task"""
    task_id = await task_processor.add_task(failing_async_func)
    await task_processor._execute_async_task(task_id, failing_async_func)

    task_data = await task_processor.get_task_result(task_id)
    assert task_data is not None
    task_data = cast(TaskData, task_data)
    assert task_data["status"] == TaskStatus.FAILED
    assert task_data["result"] is None
    assert task_data["error"] == "Test error"


@pytest.mark.asyncio
async def test_cancel_task(task_processor: BackgroundTaskProcessor):
    """Test cancelling a task"""
    task_id = await task_processor.add_task(sync_test_func)

    # Cancel pending task
    result = await task_processor.cancel_task(task_id)
    assert result is True

    task_data = await task_processor.get_task_result(task_id)
    assert task_data is not None
    task_data = cast(TaskData, task_data)
    assert task_data["status"] == TaskStatus.CANCELLED

    # Try to cancel completed task
    completed_task_id = await task_processor.add_task(sync_test_func)
    await task_processor._execute_sync_task(completed_task_id, sync_test_func)
    result = await task_processor.cancel_task(completed_task_id)
    assert result is False


@pytest.mark.asyncio
async def test_cleanup_old_tasks(task_processor: BackgroundTaskProcessor):
    """Test cleaning up old tasks"""

    async def slow_task():
        await asyncio.sleep(0.5)
        return "done"

    # Add tasks - one completes immediately, one is slow and can be cancelled
    task_id1 = await task_processor.add_task(sync_test_func)
    task_id2 = await task_processor.add_task(slow_task)

    # Wait a tiny bit to ensure the second task has started but not completed
    await asyncio.sleep(0.1)

    # Cancel the slow task before it completes
    await task_processor.cancel_task(task_id2)

    # Verify tasks are in the correct state
    task1_data = await task_processor.get_task_result(task_id1)
    task2_data = await task_processor.get_task_result(task_id2)
    assert task1_data is not None and task2_data is not None
    task1_data = cast(TaskData, task1_data)
    task2_data = cast(TaskData, task2_data)
    assert task1_data["status"] == TaskStatus.COMPLETED
    assert task2_data["status"] == TaskStatus.CANCELLED

    # Modify completion time to be old
    old_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    for task_id in [task_id1, task_id2]:
        task_key = task_processor._get_task_key(task_id)
        if task_data_str := await task_processor._redis.get(task_key):
            task_data = json.loads(task_data_str)
            task_data["completed_at"] = old_time
            await task_processor._redis.set(task_key, json.dumps(task_data))

    # Clean up tasks older than 1 hour
    cleaned = await task_processor.cleanup_old_tasks(max_age=timedelta(hours=1))
    assert cleaned == 2

    # Verify tasks were cleaned up
    assert await task_processor.get_task_result(task_id1) is None
    assert await task_processor.get_task_result(task_id2) is None


@pytest.mark.asyncio
async def test_concurrent_tasks(task_processor: BackgroundTaskProcessor):
    """Test handling concurrent tasks with semaphore"""

    async def slow_task(delay):
        await asyncio.sleep(delay)
        return delay

    # Start multiple tasks
    task_ids = []
    for _ in range(4):  # More than max_workers (2)
        task_id = await task_processor.add_task(slow_task, 0.1)
        task_ids.append(task_id)

    # Execute tasks manually
    for task_id in task_ids:
        await task_processor._execute_async_task(task_id, slow_task, 0.1)

    # Check all tasks completed successfully
    for task_id in task_ids:
        task_data = await task_processor.get_task_result(task_id)
        assert task_data is not None
        task_data = cast(TaskData, task_data)
        assert task_data["status"] == TaskStatus.COMPLETED
        assert task_data["result"] == 0.1


@pytest.mark.asyncio
async def test_custom_task_id(task_processor: BackgroundTaskProcessor):
    """Test using a custom task ID"""
    custom_id = "custom-task-123"
    task_id = await task_processor.add_task(sync_test_func, task_id=custom_id)

    assert task_id == custom_id
    task_data = await task_processor.get_task_result(custom_id)
    assert task_data is not None
    assert task_data["status"] == TaskStatus.RUNNING
