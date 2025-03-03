import asyncio
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Coroutine, Dict, Iterable, Type, TypeVar, cast

from redis.exceptions import RedisError
from redis_data_structures import SerializableType, Serializer
from redis_data_structures.config import Config

from app.config.logger import get_logger
from app.utils.async_redis_utils.connection import AsyncConnectionManager, AsyncRedisDataStructureError

try:
    from pydantic import BaseModel

    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel | SerializableType)
R = TypeVar("R")


def async_handle_operation_error(func: Callable[..., Coroutine[Any, Any, R]]) -> Callable[..., Coroutine[Any, Any, R]]:
    """Decorator for handling Redis operation errors."""

    @wraps(func)
    async def wrapper(self: "AsyncRedisDataStructure", *args: Any, **kwargs: Any) -> R:
        try:
            return await func(self, *args, **kwargs)
        except RedisError as e:
            raise e from e
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Error executing operation")
            raise AsyncRedisDataStructureError(f"Error executing operation: {e}") from e

    return wrapper


def async_atomic_operation(func: Callable[..., Coroutine[Any, Any, R]]) -> Callable[..., Coroutine[Any, Any, R]]:
    """Decorator for atomic operations."""

    @wraps(func)
    async def wrapper(self: "AsyncRedisDataStructure", *args: Any, **kwargs: Any) -> R:
        async with self._lock:
            return await func(self, *args, **kwargs)

    return wrapper


class AsyncRedisDataStructure:
    """Base class for Redis-backed data structures."""

    def __init__(
        self,
        key: str,
        connection_manager: AsyncConnectionManager | None = None,
        config: Config | None = None,
        **kwargs: Any,
    ):
        """Initialize Redis data structure."""
        self.config = config or Config.from_env()
        if kwargs:
            for key, value in kwargs.items():
                if hasattr(self.config.redis, key):
                    setattr(self.config.redis, key, value)

        self.connection_manager = connection_manager or AsyncConnectionManager(
            **self.config.redis.__dict__,
        )

        if self.config.data_structures.debug_enabled:
            logger.setLevel(logging.DEBUG)

        self.serializer = Serializer(
            compression_threshold=self.config.data_structures.compression_threshold,
        )
        self.key = f"{self.config.data_structures.prefix}:{key}"
        self._lock = asyncio.Lock()

    def _register_type(self, type_class: Type[T]) -> None:
        """Register a type for type preservation.

        Args:
            type_class: The class to register.
                        Must be either a Pydantic model or inherit from SerializableType.

        Raises:
            TypeError: If the type is not a Pydantic model or SerializableType.
        """
        if PYDANTIC_AVAILABLE and issubclass(type_class, BaseModel):
            self.serializer.pydantic_type_registry.register(type_class.__name__, type_class)
        elif issubclass(type_class, SerializableType):
            self.serializer.serializable_type_registry.register(type_class.__name__, type_class)
        else:
            raise TypeError(
                f"Type {type_class.__name__} must be a Pydantic model or inherit from SerializableType",
            )

    def register_types(self, types: Type[T] | Iterable[Type[T]] | None = None) -> None:
        """Register multiple types at once.

        Args:
            types: The types to register.

        Examples:
            Register a single type:
                register_types(types=MyType)
            Register multiple types:
                register_types(types=[MyType1, MyType2])
        """
        if types is None:
            return

        if isinstance(types, Iterable):
            for type_class in types:
                self._register_type(cast(Type[T], type_class))
        else:
            self._register_type(cast(Type[T], types))

    def get_registered_types(self) -> Dict[str, Type]:
        """Get all registered types."""
        return self.serializer.get_registered_types()

    @async_atomic_operation
    @async_handle_operation_error
    async def set_ttl(self, key: str, ttl: int | timedelta | datetime) -> bool:
        """Set Time To Live (TTL) for a key."""
        if isinstance(ttl, timedelta):
            ttl = int(ttl.total_seconds())
        elif isinstance(ttl, datetime):
            if ttl.tzinfo is None:
                ttl = int((ttl - datetime.now()).total_seconds())
            else:
                ttl = int((ttl - datetime.now(ttl.tzinfo)).total_seconds())
        else:
            ttl = int(ttl)

        if not bool(await self.connection_manager.execute("expire", key, ttl)):
            raise AsyncRedisDataStructureError(
                f"Failed to set TTL for key {key} to {ttl}. Key {key} might not exist.",
            )

        return True

    @async_atomic_operation
    @async_handle_operation_error
    async def get_ttl(self, key: str) -> Any:
        """Get remaining Time To Live (TTL) for a key."""
        return await self.connection_manager.execute("ttl", key)

    @async_atomic_operation
    @async_handle_operation_error
    async def persist(self, key: str) -> bool:
        """Remove TTL from a key."""
        return bool(await self.connection_manager.execute("persist", key))

    @async_atomic_operation
    @async_handle_operation_error
    async def clear(self) -> bool:
        """Clear all elements from the data structure."""
        return bool(await self.connection_manager.execute("delete", self.key))

    @async_atomic_operation
    @async_handle_operation_error
    async def close(self) -> None:
        """Close Redis connection."""
        await self.connection_manager.close()
