import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
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


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """Mock Redis for all tests."""

    class MockRedis:
        def __init__(self):
            self.data = {}
            self.sets = {}

        def get(self, key):
            return self.data.get(key)

        def set(self, key, value):
            self.data[key] = value

        def sadd(self, key, *values):
            if key not in self.sets:
                self.sets[key] = set()
            self.sets[key].update(values)

        def srem(self, key, *values):
            if key in self.sets:
                self.sets[key].difference_update(values)

        def smembers(self, key):
            return self.sets.get(key, set())

        def scard(self, key):
            return len(self.sets.get(key, set()))

        def ping(self):
            return True

        def info(self):
            return {"connected_clients": 1, "used_memory_human": "1M", "redis_version": "mock"}

    monkeypatch.setattr("redis.Redis", lambda **kwargs: MockRedis())
    return MockRedis()
