from typing import Any, AsyncIterator, Dict, Generic, TypeVar

from app.config.logger import get_logger
from app.utils.async_redis_utils.data_struc_base import (
    AsyncRedisDataStructure,
    async_atomic_operation,
    async_handle_operation_error,
)

logger = get_logger(__name__)

K = TypeVar("K")
V = TypeVar("V")


class AsyncLRUCache(AsyncRedisDataStructure, Generic[K, V]):
    """A Redis-backed LRU (Least Recently Used) cache implementation.

    This class implements an LRU cache using Redis lists and hashes, where the least
    recently used items are automatically removed when the cache reaches its capacity.

    All operations are optimized using Redis's native commands and pipelining for
    better performance. The implementation handles serialization of complex Python
    objects while maintaining the performance characteristics of Redis data structures.
    """

    def __init__(self, key: str, capacity: int = 1000, **kwargs: Any) -> None:
        """Initialize LRU cache.

        Args:
            key (str): The key for the LRU cache
            capacity (int): Maximum number of items in the cache
            **kwargs: Additional Redis connection parameters

        Raises:
            ValueError: If capacity is less than 1
        """
        super().__init__(key, **kwargs)
        self.capacity = max(1, capacity)  # Ensure minimum capacity of 1

    @async_atomic_operation
    @async_handle_operation_error
    async def peek(self, field: K) -> V | None:
        """Get an item from the cache without updating its access time.

        This operation is O(1) as it uses Redis's HGET command directly.
        The data is deserialized back to its original Python type.

        Args:
            field (K): The field name

        Returns:
            Optional[V]: The value if successful, None if not found
        """
        cache_key = self.key
        if self.serializer.is_redis_key_acceptable_type(field):
            data = await self.connection_manager.execute("hget", cache_key, field)
        else:
            data = await self.connection_manager.execute(
                "hget",
                cache_key,
                self.serializer.serialize(field),
            )
        if not data:
            return None

        return self.serializer.deserialize(data)  # type: ignore[no-any-return]

    @async_atomic_operation
    @async_handle_operation_error
    async def get_lru_order(self) -> list[str]:
        """Get the list of keys in LRU order (least recently used to most recently used).

        This operation is O(N) where N is the size of the cache.

        Returns:
            list[str]: List of keys in LRU order (least to most recently used)
        """
        cache_key = self.key
        data = await self.connection_manager.execute("lrange", f"{cache_key}:order", 0, -1)
        return [item.decode("utf-8") if isinstance(item, bytes) else item for item in reversed(data or [])]

    @async_atomic_operation
    @async_handle_operation_error
    async def put(self, field: K, value: V) -> bool:
        """Put an item in the cache.

        This operation is O(1) amortized as it uses Redis's pipeline to combine
        multiple operations. The least recently used item is automatically removed
        when the cache reaches its capacity.

        Args:
            field (K): The field name
            value (V): The value to store

        Returns:
            bool: True if successful, False otherwise
        """
        pipeline = self.connection_manager.pipeline()
        cache_key = self.key

        if not self.serializer.is_redis_key_acceptable_type(field):
            field = self.serializer.serialize(field)

        pipeline.lrem(f"{cache_key}:order", 0, field)  # type: ignore[arg-type]
        pipeline.lpush(f"{cache_key}:order", field)  # type: ignore[arg-type]
        pipeline.hset(cache_key, field, self.serializer.serialize(value))  # type: ignore[arg-type]

        # Check if we need to remove the least recently used item
        pipeline.llen(f"{cache_key}:order")
        results = await pipeline.execute()

        if results[-1] > self.capacity:
            # Remove the least recently used item
            lru_field = await self.connection_manager.execute("rpop", f"{cache_key}:order")
            if lru_field:
                if isinstance(lru_field, bytes):
                    lru_field = lru_field.decode("utf-8")
                await self.connection_manager.execute("hdel", cache_key, lru_field)

        return True

    @async_atomic_operation
    @async_handle_operation_error
    async def get(self, field: K) -> V | None:
        """Get an item from the cache.

        This operation is O(1) amortized as it uses Redis's pipeline to combine
        multiple operations. The item's position is updated to mark it as most
        recently used.

        Args:
            field (K): The field name

        Returns:
            Optional[V]: The value if successful, None if not found
        """
        cache_key = self.key
        if not self.serializer.is_redis_key_acceptable_type(field):
            field = self.serializer.serialize(field)

        data = await self.connection_manager.execute("hget", cache_key, field)
        if not data:
            return None

        pipeline = self.connection_manager.pipeline()
        pipeline.lrem(f"{cache_key}:order", 0, field)  # type: ignore[arg-type]
        pipeline.lpush(f"{cache_key}:order", field)  # type: ignore[arg-type]
        await pipeline.execute()

        return self.serializer.deserialize(data)  # type: ignore[no-any-return]

    @async_atomic_operation
    @async_handle_operation_error
    async def remove(self, field: K) -> bool:
        """Remove an item from the cache.

        This operation is O(1) amortized as it uses Redis's pipeline to combine
        multiple operations.

        Args:
            field (K): The field name

        Returns:
            bool: True if successful, False otherwise
        """
        cache_key = self.key
        pipeline = self.connection_manager.pipeline()
        if not self.serializer.is_redis_key_acceptable_type(field):
            field = self.serializer.serialize(field)

        pipeline.hdel(cache_key, field)  # type: ignore[arg-type]
        pipeline.lrem(f"{cache_key}:order", 0, field)  # type: ignore[arg-type]
        results = await pipeline.execute()
        return bool(results[0])

    @async_atomic_operation
    @async_handle_operation_error
    async def clear(self) -> bool:
        """Clear all items from the cache.

        This operation is O(1) as it uses Redis's pipeline to combine
        multiple DELETE operations.

        Returns:
            bool: True if successful, False otherwise
        """
        cache_key = self.key
        pipeline = self.connection_manager.pipeline()
        pipeline.delete(cache_key)
        pipeline.delete(f"{cache_key}:order")
        await pipeline.execute()
        return True

    @async_atomic_operation
    @async_handle_operation_error
    async def size(self) -> int:
        """Get the number of items in the cache.

        This operation is O(1) as it uses Redis's HLEN command directly.

        Returns:
            int: Number of items in the cache
        """
        return await self.connection_manager.execute("hlen", self.key) or 0

    @async_atomic_operation
    @async_handle_operation_error
    async def get_all(self) -> Dict[str, V]:
        """Get all items from the cache.

        This operation is O(N) where N is the size of the cache.

        Returns:
            Dict[str, V]: Dictionary of all field-value pairs in the cache
        """
        cache_key = self.key
        data = await self.connection_manager.execute("hgetall", cache_key)
        if not data:
            return {}

        return {k.decode("utf-8"): self.serializer.deserialize(v) for k, v in data.items()}

    def __aiter__(self) -> AsyncIterator[tuple[str, V]]:
        """Return an async iterator over the cache's items in LRU order."""
        return self._async_iter()

    async def _async_iter(self) -> AsyncIterator[tuple[str, V]]:
        """Helper for async iteration."""
        order = await self.get_lru_order()
        for field in order:
            value = await self.get(field)
            if value is not None:
                yield field, value

    async def __len__(self) -> int:
        """Get the number of items in the cache."""
        return await self.size()

    async def __contains__(self, field: K) -> bool:
        """Check if a field exists in the cache."""
        return await self.peek(field) is not None

    async def __getitem__(self, field: K) -> V:
        """Get an item from the cache using the subscript operator.

        This will update the item's position to mark it as most recently used.

        Raises:
            KeyError: If the field does not exist
        """
        value = await self.get(field)
        if value is None:
            raise KeyError(f"Field {field} does not exist")
        return value

    async def __setitem__(self, field: K, value: V) -> None:
        """Set an item in the cache using the subscript operator."""
        await self.put(field, value)

    async def __delitem__(self, field: K) -> None:
        """Remove an item from the cache using the subscript operator.

        Raises:
            KeyError: If the field does not exist
        """
        if not await self.remove(field):
            raise KeyError(f"Field {field} does not exist")
