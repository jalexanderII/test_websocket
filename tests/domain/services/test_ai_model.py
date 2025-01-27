import pytest
from app.domain.services.ai_model import AIModelService
from unittest.mock import Mock


@pytest.fixture
def ai_adapter_mock():
    return Mock()


@pytest.fixture
def ai_service(ai_adapter_mock):
    return AIModelService(ai_adapter_mock)


def test_generate_response(ai_service, ai_adapter_mock):
    # Arrange
    ai_adapter_mock.generate_response.return_value = "Test response"
    messages = [{"role": "user", "content": "Hello"}]

    # Act
    response = ai_service.generate_response(messages)

    # Assert
    assert response == "Test response"
    ai_adapter_mock.generate_response.assert_called_once_with(messages)
