from datetime import timedelta

from redis.asyncio import Redis as AsyncRedis
from redis_data_structures import ConnectionManager

from app.config.settings import settings

# Async Redis client for WebSocket and other async operations
async_redis = AsyncRedis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    max_connections=settings.REDIS_MAX_CONNECTIONS,
    ssl=settings.REDIS_SSL,
    decode_responses=True,  # Automatically decode responses to strings
    retry_on_timeout=True,  # Retry on timeout
    health_check_interval=30,  # Check connection health every 30 seconds
)

# Sync Redis manager (existing)
redis_manager = ConnectionManager(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    max_connections=settings.REDIS_MAX_CONNECTIONS,
    retry_max_attempts=settings.REDIS_RETRY_ATTEMPTS,
    circuit_breaker_threshold=settings.REDIS_CB_THRESHOLD,
    circuit_breaker_timeout=timedelta(minutes=settings.REDIS_CB_TIMEOUT_MINS),
    ssl=settings.REDIS_SSL,
)
