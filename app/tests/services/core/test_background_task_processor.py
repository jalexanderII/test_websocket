import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services.core.background_task_processor import BackgroundTaskProcessor, TaskStatus


@pytest.fixture
def task_processor():
    processor = BackgroundTaskProcessor(max_workers=2)
    # Clear any existing data
    processor._task_results.clear()
    return processor


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
async def test_add_task_sync(task_processor):
    """Test adding a synchronous task"""
    task_id = await task_processor.add_task(sync_test_func, 1, 2, kwarg1="test")

    # Check initial task state
    task_data = await task_processor.get_task_result(task_id)
    assert task_data is not None
    assert task_data["status"] == TaskStatus.PENDING  # type: ignore
    assert task_data["result"] is None  # type: ignore
    assert task_data["error"] is None  # type: ignore
    assert "created_at" in task_data
    assert "updated_at" in task_data


@pytest.mark.asyncio
async def test_add_task_async(task_processor):
    """Test adding an asynchronous task"""
    task_id = await task_processor.add_task(async_test_func, 1, 2, kwarg1="test")

    # Check initial task state
    task_data = await task_processor.get_task_result(task_id)
    assert task_data is not None
    assert task_data["status"] == TaskStatus.PENDING  # type: ignore
    assert task_data["result"] is None  # type: ignore
    assert task_data["error"] is None  # type: ignore


@pytest.mark.asyncio
async def test_execute_sync_task(task_processor):
    """Test executing a synchronous task"""
    task_id = await task_processor.add_task(sync_test_func, 1, 2, kwarg1="test")
    await task_processor._execute_sync_task(task_id, sync_test_func, 1, 2, kwarg1="test")

    task_data = await task_processor.get_task_result(task_id)
    assert task_data["status"] == TaskStatus.COMPLETED  # type: ignore
    assert task_data["result"] == {"args": [1, 2], "kwargs": {"kwarg1": "test"}}  # type: ignore
    assert task_data["error"] is None  # type: ignore


@pytest.mark.asyncio
async def test_execute_async_task(task_processor):
    """Test executing an asynchronous task"""
    task_id = await task_processor.add_task(async_test_func, 1, 2, kwarg1="test")
    await task_processor._execute_async_task(task_id, async_test_func, 1, 2, kwarg1="test")

    task_data = await task_processor.get_task_result(task_id)
    assert task_data["status"] == TaskStatus.COMPLETED  # type: ignore
    assert task_data["result"] == {"args": [1, 2], "kwargs": {"kwarg1": "test"}}  # type: ignore
    assert task_data["error"] is None  # type: ignore


@pytest.mark.asyncio
async def test_failing_sync_task(task_processor):
    """Test handling a failing synchronous task"""
    task_id = await task_processor.add_task(failing_sync_func)
    await task_processor._execute_sync_task(task_id, failing_sync_func)

    task_data = await task_processor.get_task_result(task_id)
    assert task_data["status"] == TaskStatus.FAILED  # type: ignore
    assert task_data["result"] is None  # type: ignore
    assert task_data["error"] == "Test error"  # type: ignore


@pytest.mark.asyncio
async def test_failing_async_task(task_processor):
    """Test handling a failing asynchronous task"""
    task_id = await task_processor.add_task(failing_async_func)
    await task_processor._execute_async_task(task_id, failing_async_func)

    task_data = await task_processor.get_task_result(task_id)
    assert task_data["status"] == TaskStatus.FAILED  # type: ignore
    assert task_data["result"] is None  # type: ignore
    assert task_data["error"] == "Test error"  # type: ignore


@pytest.mark.asyncio
async def test_cancel_task(task_processor):
    """Test cancelling a task"""
    task_id = await task_processor.add_task(sync_test_func)

    # Cancel pending task
    result = await task_processor.cancel_task(task_id)
    assert result is True

    task_data = await task_processor.get_task_result(task_id)
    assert task_data["status"] == TaskStatus.CANCELLED  # type: ignore

    # Try to cancel completed task
    completed_task_id = await task_processor.add_task(sync_test_func)
    await task_processor._execute_sync_task(completed_task_id, sync_test_func)
    result = await task_processor.cancel_task(completed_task_id)
    assert result is False


@pytest.mark.asyncio
async def test_cleanup_old_tasks(task_processor):
    """Test cleaning up old tasks"""
    # Add some tasks
    task_id1 = await task_processor.add_task(sync_test_func)
    task_id2 = await task_processor.add_task(sync_test_func)

    # Complete one task
    await task_processor._execute_sync_task(task_id1, sync_test_func)

    # Cancel one task
    await task_processor.cancel_task(task_id2)

    # Modify completion time to be old
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    for task_id in [task_id1, task_id2]:
        if task_data := task_processor._task_results.get(task_id):
            task_data["completed_at"] = old_time  # type: ignore
            task_processor._task_results[task_id] = task_data  # type: ignore

    # Clean up tasks older than 1 hour
    cleaned = await task_processor.cleanup_old_tasks(max_age=timedelta(hours=1))
    assert cleaned == 2

    # Verify tasks were cleaned up
    assert await task_processor.get_task_result(task_id1) is None
    assert await task_processor.get_task_result(task_id2) is None


@pytest.mark.asyncio
async def test_concurrent_tasks(task_processor):
    """Test handling concurrent tasks with semaphore"""

    async def slow_task(delay):
        await asyncio.sleep(delay)
        return delay

    # Start multiple tasks
    task_ids = []
    for i in range(4):  # More than max_workers (2)
        task_id = await task_processor.add_task(slow_task, 0.1)
        task_ids.append(task_id)
        await task_processor._execute_async_task(task_id, slow_task, 0.1)

    # Check all tasks completed
    for task_id in task_ids:
        task_data = await task_processor.get_task_result(task_id)
        assert task_data["status"] == TaskStatus.COMPLETED  # type: ignore
        assert task_data["result"] == 0.1  # type: ignore


@pytest.mark.asyncio
async def test_custom_task_id(task_processor):
    """Test using a custom task ID"""
    custom_id = "custom-task-123"
    task_id = await task_processor.add_task(sync_test_func, task_id=custom_id)

    assert task_id == custom_id
    task_data = await task_processor.get_task_result(custom_id)
    assert task_data is not None
    assert task_data["status"] == TaskStatus.PENDING  # type: ignore
