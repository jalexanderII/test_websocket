import pytest
from app.infrastructure.adapters.ai_adapter import AIAdapter
from unittest.mock import patch


@pytest.fixture
def ai_adapter():
    return AIAdapter()


@patch("app.infrastructure.adapters.ai_adapter.openai.ChatCompletion.create")
def test_generate_response(mock_create, ai_adapter):
    # Arrange
    mock_create.return_value = {"choices": [{"message": {"content": "Test response"}}]}
    messages = [{"role": "user", "content": "Hello"}]

    # Act
    response = ai_adapter.generate_response(messages)

    # Assert
    assert response == "Test response"
    mock_create.assert_called_once()
