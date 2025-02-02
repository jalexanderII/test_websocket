from datetime import timedelta

from app.config.settings import settings
from app.utils.async_redis_utils.connection import AsyncConnectionManager

async_redis = AsyncConnectionManager(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    max_connections=settings.REDIS_MAX_CONNECTIONS,
    retry_max_attempts=settings.REDIS_RETRY_ATTEMPTS,
    circuit_breaker_threshold=settings.REDIS_CB_THRESHOLD,
    circuit_breaker_timeout=timedelta(minutes=settings.REDIS_CB_TIMEOUT_MINS),
    ssl=settings.REDIS_SSL,
)
