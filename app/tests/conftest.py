import os
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis_data_structures import ConnectionManager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.database import Base, get_db
from app.config.redis import async_redis
from app.main import app

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """Create a test client with a fresh database session."""

    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def redis_config() -> dict:
    """Get Redis configuration from environment or defaults."""
    return {
        "host": os.getenv("TEST_REDIS_HOST", "localhost"),
        "port": int(os.getenv("TEST_REDIS_PORT", "6379")),
        "db": int(os.getenv("TEST_REDIS_DB", "0")),
    }


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis, None]:
    """Create a Redis client for testing."""
    try:
        await async_redis.ping()
        yield async_redis
    finally:
        await async_redis.aclose()


@pytest.fixture(scope="session")
def connection_manager(redis_config: dict) -> ConnectionManager:
    """Create a ConnectionManager instance for testing."""
    return ConnectionManager(**redis_config)


@pytest_asyncio.fixture(autouse=True)
async def clean_redis(redis_client: Redis) -> AsyncGenerator[None, None]:
    """Clean Redis database before and after each test."""
    await redis_client.flushdb()
    yield
    await redis_client.flushdb()


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock environment variables for testing"""
    with patch.dict(
        "os.environ",
        {
            "OPENAI_API_KEY": "test-key",
            "MODEL_NAME": "test-model",
        },
    ):
        yield
