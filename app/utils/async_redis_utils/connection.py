import time
from datetime import timedelta
from typing import Any, Dict

import backoff
from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import RedisError

from app.config.logger import get_logger

logger = get_logger(__name__)


class AsyncRedisDataStructureError(Exception):
    """Base exception for all Redis data structure errors."""


class AsyncRedisConnectionError(AsyncRedisDataStructureError):
    """Raised when there are connection issues with Redis."""


class AsyncSerializationError(AsyncRedisDataStructureError):
    """Raised when there are issues serializing/deserializing data."""


class AsyncOperationError(AsyncRedisDataStructureError):
    """Raised when a Redis operation fails."""


class AsyncValidationError(AsyncRedisDataStructureError):
    """Raised when data validation fails."""


class AsyncConfigurationError(AsyncRedisDataStructureError):
    """Raised when there are configuration issues."""


class AsyncCircuitBreakerError(AsyncRedisDataStructureError):
    """Raised when the circuit breaker is open."""


class AsyncConnectionManager:
    """Manages Redis connections with advanced features like connection pooling, automatic reconnection, and circuit breaking."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        socket_timeout: float | None = None,
        connection_pool: ConnectionPool | None = None,
        max_connections: int = 10,
        retry_max_attempts: int = 3,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: timedelta = timedelta(seconds=60),
        ssl: bool = False,
        ssl_cert_reqs: str | None = None,
        ssl_ca_certs: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the connection manager.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password
            socket_timeout: Socket timeout in seconds
            connection_pool: Optional pre-configured connection pool
            max_connections: Maximum number of connections in the pool
            retry_max_attempts: Maximum number of retry attempts
            circuit_breaker_threshold: Number of failures before circuit breaks
            circuit_breaker_timeout: How long to wait before retrying after circuit breaks
            ssl: Whether to use SSL/TLS for the connection
            ssl_cert_reqs: SSL certificate requirements ('none', 'optional', or 'required')
            ssl_ca_certs: Path to the CA certificate file
            **kwargs: Additional keyword arguments for the Redis connection
        """
        # Filter out None values to avoid passing them to Redis
        connection_params = {
            "host": host,
            "port": port,
            "db": db,
        }

        # Add optional parameters only if they are not None
        if password is not None:
            connection_params["password"] = password
        if socket_timeout is not None:
            connection_params["socket_timeout"] = socket_timeout
        if ssl:
            connection_params["ssl"] = True
            if ssl_cert_reqs:
                connection_params["ssl_cert_reqs"] = ssl_cert_reqs
            if ssl_ca_certs:
                connection_params["ssl_ca_certs"] = ssl_ca_certs

        # Add any remaining kwargs
        connection_params.update({k: v for k, v in kwargs.items() if v is not None})

        self.connection_params = connection_params
        self._pool = connection_pool or ConnectionPool(
            max_connections=max_connections,
            **connection_params,  # type: ignore[arg-type]
        )

        self._client: Redis | None = None
        self._failure_count = 0
        self._circuit_breaker_threshold = circuit_breaker_threshold
        self._circuit_breaker_timeout = circuit_breaker_timeout
        self._retry_max_attempts = retry_max_attempts

    @property
    def client(self) -> Redis:
        """Get Redis client, creating it if necessary."""
        if self._client is None:
            self._client = Redis(connection_pool=self._pool)
        return self._client

    @backoff.on_exception(
        backoff.expo,
        (RedisError, ConnectionError, AsyncCircuitBreakerError),
        max_tries=3,
        jitter=None,
        on_backoff=lambda details: logger.warning(
            "Retrying Redis connection after %.2fs",
            details.get("wait", 0),
        ),
    )
    async def execute(self, func_name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a Redis command with automatic retries and circuit breaking.

        Args:
            func_name: Name of the Redis command to execute
            *args: Positional arguments for the command
            **kwargs: Keyword arguments for the command

        Returns:
            The result of the Redis command

        Raises:
            RedisError: If the command fails after retries
        """
        if self._failure_count >= self._circuit_breaker_threshold:
            logger.error("Circuit breaker is open, Redis commands are blocked")
            raise RedisError("Circuit breaker is open") from None

        try:
            func = getattr(self.client, func_name)
            result = await func(*args, **kwargs)
            self._failure_count = 0  # Reset on success
            return result
        except (RedisError, ConnectionError, AsyncCircuitBreakerError):
            self._failure_count += 1
            logger.exception("Redis command failed: %s", func_name)
            raise AsyncCircuitBreakerError("Circuit breaker is open") from None

    def pipeline(self) -> Pipeline:
        """Get a Redis pipeline for batch operations."""
        return self.client.pipeline()

    async def health_check(self) -> Dict[str, Any]:
        """Check Redis connection health.

        Returns:
            Dict with health check information
        """
        try:
            start_time = time.time()
            await self.client.ping()
            latency = (time.time() - start_time) * 1000  # Convert to milliseconds

            info = await self.client.info()
            pool_info = {
                "max_connections": self._pool.max_connections if self._pool else 0,
                "current_connections": len(self._pool._in_use_connections) if self._pool else 0,
                "available_connections": len(self._pool._available_connections) if self._pool else 0,
            }

            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "connected_clients": info.get("connected_clients"),
                "used_memory": info.get("used_memory_human"),
                "version": info.get("redis_version"),
                "connection_pool": pool_info,
                "circuit_breaker": {
                    "failure_count": self._failure_count,
                    "threshold": self._circuit_breaker_threshold,
                    "timeout": self._circuit_breaker_timeout.total_seconds(),
                },
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "circuit_breaker": {
                    "failure_count": self._failure_count,
                    "threshold": self._circuit_breaker_threshold,
                },
            }

    async def close(self) -> None:
        """Close all connections in the pool."""
        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None  # type: ignore[assignment]
