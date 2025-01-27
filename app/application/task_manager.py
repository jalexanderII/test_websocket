from typing import Dict, Coroutine
import asyncio

class TaskManager:
    _tasks: Dict[str, asyncio.Task] = {}

    @classmethod
    def create_task(cls, task_id: str, coro: Coroutine) -> asyncio.Task:
        task = asyncio.create_task(coro)
        cls._tasks[task_id] = task
        return task

    @classmethod
    def get_task(cls, task_id: str) -> asyncio.Task:
        if task_id not in cls._tasks:
            raise KeyError(f"Task {task_id} not found")
        return cls._tasks[task_id]

    @classmethod
    def cancel_task(cls, task_id: str) -> bool:
        task = cls._tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    @classmethod
    def remove_task(cls, task_id: str) -> None:
        if task_id in cls._tasks:
            del cls._tasks[task_id]

    @classmethod
    def cleanup_finished_tasks(cls) -> None:
        finished_tasks = [
            task_id for task_id, task in cls._tasks.items()
            if task.done()
        ]
        for task_id in finished_tasks:
            cls.remove_task(task_id) 