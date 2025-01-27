import pytest
from app.infrastructure.db.database import Database
from app.config import TestConfig


@pytest.fixture
def test_db():
    """Fixture to provide a test database instance"""
    db = Database(TestConfig.DATABASE_URL)
    # Setup
    yield db
    # Teardown - clear test data
    db.clear_all()


@pytest.fixture
def test_client():
    """Fixture to provide a test client"""
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)
