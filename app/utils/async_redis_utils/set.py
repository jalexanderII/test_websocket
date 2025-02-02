from typing import AsyncIterator, Generic, List, TypeVar

from app.config.logger import get_logger
from app.utils.async_redis_utils.data_struc_base import (
    AsyncRedisDataStructure,
    async_atomic_operation,
    async_handle_operation_error,
)

logger = get_logger(__name__)

T = TypeVar("T")


class AsyncSet(AsyncRedisDataStructure, Generic[T]):
    """A Redis-backed set implementation.

    This class implements a set data structure using Redis sets, ensuring uniqueness
    of elements and providing O(1) add/remove operations. It's perfect for tracking
    unique items like user sessions, maintaining lists of unique identifiers, and
    implementing features that require set operations like unions and intersections.

    All operations (add, remove, contains) are O(1) as they leverage Redis's native
    set operations. The implementation handles serialization of complex Python objects
    while maintaining the performance characteristics of Redis sets.
    """

    @async_atomic_operation
    @async_handle_operation_error
    async def members(self) -> List[T]:
        """Get all members of the set.

        This operation is O(N) where N is the size of the set.
        All items are deserialized back to their original Python types.

        Returns:
            List[T]: List of all members with their original types
        """
        items = await self.connection_manager.execute("smembers", self.key)
        if not items:
            return []

        return [self.serializer.deserialize(item) for item in items]

    @async_atomic_operation
    @async_handle_operation_error
    async def pop(self) -> T | None:
        """Remove and return a random element from the set.

        This operation is O(1) as it uses Redis's SPOP command directly.

        Returns:
            Optional[T]: Random element if successful, None if set is empty
        """
        data = await self.connection_manager.execute("spop", self.key)
        return self.serializer.deserialize(data) if data else None

    @async_atomic_operation
    @async_handle_operation_error
    async def add(self, data: T) -> bool:
        """Add an item to the set.

        This operation is O(1) as it uses Redis's SADD command directly.
        The data is serialized with type information to ensure proper
        deserialization later.

        Args:
            data (T): Data to be stored. Can be any serializable Python object.

        Returns:
            bool: True if the item was added, False if it was already present
        """
        serialized = self.serializer.serialize(data)
        result = await self.connection_manager.execute("sadd", self.key, serialized)
        return bool(result)  # sadd returns 1 if added, 0 if already exists

    @async_atomic_operation
    @async_handle_operation_error
    async def remove(self, data: T) -> bool:
        """Remove an item from the set.

        This operation is O(1) as it uses Redis's SREM command directly.
        The data is serialized to match the stored format for removal.

        Args:
            data (T): Data to be removed

        Returns:
            bool: True if the item was removed, False if it wasn't present
        """
        serialized = self.serializer.serialize(data)
        result = await self.connection_manager.execute("srem", self.key, serialized)
        return bool(result)  # srem returns 1 if removed, 0 if not found

    @async_atomic_operation
    @async_handle_operation_error
    async def contains(self, data: T) -> bool:
        """Check if an item exists in the set.

        This operation is O(1) as it uses Redis's SISMEMBER command directly.
        The data is serialized to match the stored format for comparison.

        Args:
            data (T): Data to check for existence

        Returns:
            bool: True if the item exists, False otherwise
        """
        serialized = self.serializer.serialize(data)
        result = await self.connection_manager.execute("sismember", self.key, serialized)
        return bool(result)  # sismember returns 1 if exists, 0 otherwise

    @async_atomic_operation
    @async_handle_operation_error
    async def size(self) -> int:
        """Get the number of items in the set.

        This operation is O(1) as it uses Redis's SCARD command directly.

        Returns:
            int: Number of items in the set
        """
        result = await self.connection_manager.execute("scard", self.key)
        return int(result)  # scard returns integer count

    @async_atomic_operation
    @async_handle_operation_error
    async def clear(self) -> bool:
        """Remove all elements from the set.

        This operation is O(1) as it uses Redis's DELETE command directly.

        Returns:
            bool: True if successful, False otherwise
        """
        await self.connection_manager.execute("delete", self.key)
        return True

    async def __contains__(self, item: T) -> bool:
        """Check if an item exists in the set."""
        return await self.contains(item)

    def __aiter__(self) -> AsyncIterator[T]:
        """Return an async iterator over the set's items."""
        return self._async_iter()

    async def _async_iter(self) -> AsyncIterator[T]:
        """Helper for async iteration."""
        items = await self.members()
        for item in items:
            yield item

    async def __len__(self) -> int:
        """Get the number of items in the set."""
        return await self.size()

    async def __repr__(self) -> str:
        """Return a string representation of the set."""
        items = await self.members()
        return f"AsyncSet(key={self.key}, items={items})"

    async def __str__(self) -> str:
        """Return a string representation of the set."""
        items = await self.members()
        return str(items)
