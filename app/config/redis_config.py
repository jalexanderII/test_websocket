from redis_data_structures import ConnectionManager
from datetime import timedelta
from config.env import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_MAX_CONNECTIONS,
    REDIS_RETRY_ATTEMPTS,
    REDIS_CB_THRESHOLD,
    REDIS_CB_TIMEOUT_MINS,
    REDIS_SSL,
)

# Initialize a single Redis connection manager for the entire application
redis_manager = ConnectionManager(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    max_connections=REDIS_MAX_CONNECTIONS,
    retry_max_attempts=REDIS_RETRY_ATTEMPTS,
    circuit_breaker_threshold=REDIS_CB_THRESHOLD,
    circuit_breaker_timeout=timedelta(
        minutes=REDIS_CB_TIMEOUT_MINS,
    ),
    ssl=REDIS_SSL,
)
