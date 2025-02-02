import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # General settings
    debug: str = "False"
    docs_url: str = "/docs"
    openapi_prefix: str = ""
    openapi_url: str = "/openapi.json"
    redoc_url: str = "/redoc"
    title: str = "Websocket Chat"
    version: str = "0.1.0"

    # Custom settings
    disable_docs: bool = False

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chat.db")

    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")

    # Server
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8005"))
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    # Validate required environment variables
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    # Redis Configuration
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))
    REDIS_RETRY_ATTEMPTS = int(os.getenv("REDIS_RETRY_ATTEMPTS", "5"))
    REDIS_CB_THRESHOLD = int(os.getenv("REDIS_CB_THRESHOLD", "10"))
    REDIS_CB_TIMEOUT_MINS = int(os.getenv("REDIS_CB_TIMEOUT_MINS", "5"))
    REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() == "true"

    # Background Task Processor
    BACKGROUND_TASK_PROCESSOR_MAX_WORKERS = int(os.getenv("MAX_WORKERS", (os.cpu_count() or 1) * 5))

    @property
    def fastapi_kwargs(self) -> dict[str, bool | str | None]:
        """
        This returns a dictionary of the most commonly used keyword arguments when initializing a FastAPI instance

        If `self.disable_docs` is True, the various docs-related arguments are disabled, preventing your spec from being
        published.
        """
        fastapi_kwargs: dict[str, bool | str | None] = {
            "debug": False if self.debug == "False" else True,
            "docs_url": self.docs_url,
            "openapi_prefix": self.openapi_prefix,
            "openapi_url": self.openapi_url,
            "redoc_url": self.redoc_url,
            "title": self.title,
            "version": self.version,
        }
        if self.disable_docs:
            fastapi_kwargs.update({"docs_url": None, "openapi_url": None, "redoc_url": None})
        return fastapi_kwargs


@lru_cache
def get_api_settings() -> Settings:
    """
    This function returns a cached instance of the Settings object.

    Caching is used to prevent re-reading the environment every time the API settings are used in an endpoint.

    If you want to change an environment variable and reset the cache (e.g., during testing), this can be done
    using the `lru_cache` instance method `get_api_settings.cache_clear()`.
    """
    return Settings()


settings = get_api_settings()
