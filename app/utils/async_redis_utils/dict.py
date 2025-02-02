from typing import Any, AsyncIterator, Dict as DictType, Generic, List, Tuple, TypeVar

from app.config.logger import get_logger
from app.utils.async_redis_utils.data_struc_base import (
    AsyncRedisDataStructure,
    async_atomic_operation,
    async_handle_operation_error,
)

logger = get_logger(__name__)

K = TypeVar("K")
V = TypeVar("V")


class AsyncDict(AsyncRedisDataStructure, Generic[K, V]):
    """A python-like dictionary data structure for Redis with separate redis key if you don't want to use HashMap with `HSET` and `HGET` commands."""

    def __init__(self, key: str, *args: Any, **kwargs: Any) -> None:
        """Initialize the Dict data structure.

        Args:
            key: The key for the dictionary
            *args: Additional arguments
            **kwargs: Additional keyword arguments
        """
        super().__init__(key, *args, **kwargs)
        self.key = key
        self.key_separator = "`"

    @async_atomic_operation
    @async_handle_operation_error
    async def set(self, key: K, value: V) -> bool:
        """Set a key-value pair in the dictionary.

        Args:
            key: The key to set.
            value: The value to set.

        Returns:
            bool: True if the key-value pair was set successfully, False otherwise.
        """
        key = self.serializer.serialize(key, force_compression=False, decode=True)
        actual_key = f"{self.config.data_structures.prefix}{self.key_separator}{self.key}{self.key_separator}{key}"
        serialized_value = self.serializer.serialize(value)
        return bool(await self.connection_manager.execute("set", actual_key, serialized_value))

    @async_atomic_operation
    @async_handle_operation_error
    async def get(self, key: K) -> V:
        """Get a value from the dictionary.

        Args:
            key: The key to get.

        Returns:
            Any: The value associated with the key.
        """
        key = self.serializer.serialize(key, force_compression=False, decode=True)
        actual_key = f"{self.config.data_structures.prefix}{self.key_separator}{self.key}{self.key_separator}{key}"
        serialized_value = await self.connection_manager.execute("get", actual_key)
        return self.serializer.deserialize(serialized_value)  # type: ignore[no-any-return]

    @async_atomic_operation
    @async_handle_operation_error
    async def delete(self, key: K) -> bool:
        """Delete a key-value pair from the dictionary.

        Args:
            key: The key to delete.

        Returns:
            bool: True if the key-value pair was deleted successfully, False otherwise.
        """
        key = self.serializer.serialize(key, force_compression=False, decode=True)
        actual_key = f"{self.config.data_structures.prefix}{self.key_separator}{self.key}{self.key_separator}{key}"
        return bool(await self.connection_manager.execute("delete", actual_key))

    @async_atomic_operation
    @async_handle_operation_error
    async def keys(self) -> List[K]:
        """Get all keys in the dictionary.

        Returns:
            List[str]: A list of all keys in the dictionary.
        """
        pattern = f"{self.config.data_structures.prefix}{self.key_separator}{self.key}{self.key_separator}*"
        keys = await self.connection_manager.execute("keys", pattern)
        k = [key.decode().split(self.key_separator)[-1] for key in keys]
        return [self.serializer.deserialize(key.encode()) for key in k]

    @async_atomic_operation
    @async_handle_operation_error
    async def values(self) -> List[V]:
        """Get all values in the dictionary.

        Returns:
            List[T]: A list of all values in the dictionary.
        """
        keys = await self.keys()
        values = []
        for key in keys:
            value = await self.get(key)
            values.append(value)
        return values

    @async_atomic_operation
    @async_handle_operation_error
    async def items(self) -> List[Tuple[K, V]]:
        """Get all key-value pairs in the dictionary.

        Returns:
            List[Tuple[str, T]]: A list of all key-value pairs in the dictionary.
        """
        keys = await self.keys()
        items = []
        for key in keys:
            value = await self.get(key)
            items.append((key, value))
        return items

    @async_atomic_operation
    @async_handle_operation_error
    async def clear(self) -> bool:
        """Clear the dictionary."""
        keys = await self.keys()
        for key in keys:
            await self.delete(key)
        return True

    @async_atomic_operation
    @async_handle_operation_error
    async def exists(self, key: K) -> bool:
        """Check if a key exists in the dictionary."""
        key = self.serializer.serialize(key, force_compression=False, decode=True)
        actual_key = f"{self.config.data_structures.prefix}{self.key_separator}{self.key}{self.key_separator}{key}"
        return bool(await self.connection_manager.execute("exists", actual_key))

    @async_atomic_operation
    @async_handle_operation_error
    async def size(self) -> int:
        """Get the number of key-value pairs in the dictionary."""
        keys = await self.keys()
        return len(keys)

    async def __contains__(self, key: K) -> bool:
        """Check if a key exists in the dictionary."""
        return await self.exists(key)

    async def __getitem__(self, key: K) -> V:
        """Get a value from the dictionary using the subscript operator.

        Args:
            key: The key to get.

        Returns:
            T: The value associated with the key.

        Raises:
            KeyError: If the key does not exist.
        """
        value = await self.get(key)
        if value is None:
            raise KeyError(f"Key {key} does not exist")
        return value

    async def __setitem__(self, key: K, value: V) -> None:
        """Set a value in the dictionary using the subscript operator."""
        await self.set(key, value)

    async def __delitem__(self, key: K) -> None:
        """Delete a key-value pair from the dictionary using the subscript operator.

        Args:
            key: The key to delete.

        Raises:
            KeyError: If the key does not exist.
        """
        if not await self.exists(key):
            raise KeyError(f"Key {key} does not exist")
        await self.delete(key)

    def __aiter__(self) -> AsyncIterator[K]:
        """Iterate over the keys in the dictionary."""
        return self._async_iter()

    async def _async_iter(self) -> AsyncIterator[K]:
        """Helper for async iteration."""
        keys = await self.keys()
        for key in keys:
            yield key

    async def __len__(self) -> int:
        """Get the number of key-value pairs in the dictionary."""
        return await self.size()

    async def __repr__(self) -> str:
        """Return a string representation of the dictionary."""
        items = await self.items()
        return f"Dict(key={self.key}, items={items})"

    async def __str__(self) -> str:
        """Return a string representation of the dictionary."""
        d = await self.to_dict()
        return str(d)

    async def __eq__(self, other: object) -> bool:
        """Check if the dictionary is equal to another dictionary."""
        if not isinstance(other, AsyncDict):
            return False

        return await self.to_dict() == await other.to_dict()

    async def to_dict(self) -> DictType[K, V]:
        """Return a dictionary representation of the dictionary."""
        items = await self.items()
        return dict(items)
