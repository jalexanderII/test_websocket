from typing import AsyncIterator, Generic, TypeVar

from app.config.logger import get_logger
from app.utils.async_redis_utils.data_struc_base import (
    AsyncRedisDataStructure,
    async_atomic_operation,
    async_handle_operation_error,
)

logger = get_logger(__name__)

T = TypeVar("T")


class AsyncQueue(AsyncRedisDataStructure, Generic[T]):
    """A Redis-backed FIFO (First-In-First-Out) queue implementation.

    This class implements a queue data structure using Redis lists, where elements
    are added to the back and removed from the front, following FIFO order.

    All operations are O(1) as they leverage Redis's native list operations.
    The implementation handles serialization of complex Python objects while
    maintaining the performance characteristics of Redis lists.
    """

    @async_atomic_operation
    @async_handle_operation_error
    async def push(self, data: T) -> bool:
        """Push an item to the back of the queue.

        This operation is O(1) as it uses Redis's RPUSH command directly.
        The data is serialized with type information to ensure proper
        deserialization later.

        Args:
            data (T): Data to be stored. Can be any serializable Python object.

        Returns:
            bool: True if successful, False otherwise
        """
        serialized = self.serializer.serialize(data)
        return bool(await self.connection_manager.execute("rpush", self.key, serialized))

    @async_atomic_operation
    @async_handle_operation_error
    async def pop(self) -> T | None:
        """Pop an item from the front of the queue.

        This operation is O(1) as it uses Redis's LPOP command directly.
        The data is deserialized back to its original Python type.

        Returns:
            Optional[T]: The data if successful, None if queue is empty
        """
        data = await self.connection_manager.execute("lpop", self.key)
        return self.serializer.deserialize(data) if data else None

    @async_atomic_operation
    @async_handle_operation_error
    async def peek(self) -> T | None:
        """Peek at the front item without removing it.

        This operation is O(1) as it uses Redis's LINDEX command directly.
        The data is deserialized back to its original Python type.

        Returns:
            Optional[T]: The data if successful, None if queue is empty
        """
        data = await self.connection_manager.execute("lindex", self.key, 0)
        return self.serializer.deserialize(data) if data else None

    @async_atomic_operation
    @async_handle_operation_error
    async def size(self) -> int:
        """Get the number of items in the queue.

        This operation is O(1) as it uses Redis's LLEN command directly.

        Returns:
            int: Number of items in the queue
        """
        return await self.connection_manager.execute("llen", self.key) or 0

    @async_atomic_operation
    @async_handle_operation_error
    async def clear(self) -> bool:
        """Clear all items from the queue.

        This operation is O(1) as it uses Redis's DELETE command directly.

        Returns:
            bool: True if successful, False otherwise
        """
        await self.connection_manager.execute("delete", self.key)
        return True

    def __aiter__(self) -> AsyncIterator[T]:
        """Return an async iterator over the queue's items."""
        return self._async_iter()

    async def _async_iter(self) -> AsyncIterator[T]:
        """Helper for async iteration.

        Note: This will consume the queue as it iterates.
        """
        while True:
            item = await self.pop()
            if item is None:
                break
            yield item

    async def __len__(self) -> int:
        """Get the number of items in the queue."""
        return await self.size()

    async def __repr__(self) -> str:
        """Return a string representation of the queue."""
        size = await self.size()
        peek = await self.peek()
        return f"AsyncQueue(key={self.key}, size={size}, front={peek})"

    async def __str__(self) -> str:
        """Return a string representation of the queue."""
        size = await self.size()
        peek = await self.peek()
        return f"Queue(size={size}, front={peek})"
