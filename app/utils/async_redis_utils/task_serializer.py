from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict

from redis_data_structures import SerializableType


class SerializableTask(SerializableType):
    """A serializable wrapper for asyncio.Task objects."""

    _task_store: Dict[str, asyncio.Task] = {}  # Class-level task store

    def __init__(self, task: asyncio.Task | None = None):
        self.task = task
        self.task_id = str(uuid.uuid4()) if task else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to a dictionary for serialization."""
        if self.task and self.task_id:  # Ensure task_id is not None
            self._task_store[self.task_id] = self.task
            return {"task_id": self.task_id}
        return {"task_id": None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SerializableTask:
        """Create a SerializableTask from a dictionary."""
        instance = cls()
        instance.task_id = data.get("task_id")
        if instance.task_id:
            instance.task = cls._task_store.get(instance.task_id)
        return instance

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SerializableTask):
            return NotImplemented
        return self.task_id == other.task_id

    def __hash__(self) -> int:
        return hash(self.task_id)

    # Delegate task methods
    def cancel(self) -> bool:
        """Cancel the task."""
        if self.task:
            return self.task.cancel()
        return False

    def done(self) -> bool:
        """Return True if the task is done."""
        if self.task:
            return self.task.done()
        return False

    def cancelled(self) -> bool:
        """Return True if the task was cancelled."""
        if self.task:
            return self.task.cancelled()
        return False

    def get_name(self) -> str | None:
        """Get the task's name."""
        if self.task:
            return self.task.get_name()
        return None

    def get_coro(self) -> Any:
        """Get the coroutine object wrapped by the task."""
        if self.task:
            return self.task.get_coro()
        return None

    def __await__(self):
        """Make SerializableTask awaitable by delegating to the underlying task."""
        if self.task is None:
            raise RuntimeError("Cannot await SerializableTask with no underlying task")
        return self.task.__await__()

    def get_task(self) -> asyncio.Task | None:
        return self.task
