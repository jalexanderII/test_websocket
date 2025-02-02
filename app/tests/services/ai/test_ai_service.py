from typing import AsyncGenerator, Sequence
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.services.ai.adapter import ChatMessage
from app.services.ai.service import AIService


class MockResponse(BaseModel):
    """Test response model"""

    answer: str
    details: str


async def mock_stream_response(prompt: str, history: Sequence[ChatMessage] | None = None) -> AsyncGenerator[str, None]:
    """Mock implementation of stream_response"""
    tokens = ["Hello", " World", "!"]
    for token in tokens:
        yield token


async def mock_structured_stream(
    prompt: str,
    response_model: type[BaseModel],
    history: Sequence[ChatMessage] | None = None,
) -> AsyncGenerator[MockResponse, None]:
    """Mock implementation of stream_structured_response"""
    responses = [
        MockResponse(answer="First", details="Details 1"),
        MockResponse(answer="Second", details="Details 2"),
    ]
    for response in responses:
        yield response


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.stream_response = mock_stream_response
    adapter.stream_structured_response = mock_structured_stream
    adapter.generate_response = AsyncMock(return_value="Hello World!")
    return adapter


@pytest.fixture
def ai_service(mock_adapter):
    return AIService(adapter=mock_adapter)


@pytest.mark.asyncio
async def test_stream_chat_response(ai_service):
    # Test streaming chat response
    message = "Test message"
    history = [{"role": "user", "content": "Previous message"}]

    tokens = []
    async for token in ai_service.stream_chat_response(message, history=history):
        tokens.append(token)

    assert tokens == ["Hello", " World", "!"]


@pytest.mark.asyncio
async def test_stream_structured_response(ai_service):
    # Test streaming structured response
    message = "Test message"
    history = [{"role": "user", "content": "Previous message"}]

    responses = []
    async for response in ai_service.stream_structured_response(message, MockResponse, history=history):
        responses.append(response)

    assert len(responses) == 2
    assert all(isinstance(r, MockResponse) for r in responses)
    assert [r.answer for r in responses] == ["First", "Second"]
    assert [r.details for r in responses] == ["Details 1", "Details 2"]


@pytest.mark.asyncio
async def test_get_completion(ai_service):
    # Test getting a complete response
    message = "Test message"
    history = [{"role": "user", "content": "Previous message"}]

    response = await ai_service.get_completion(message, history=history)
    assert response == "Hello World!"


async def error_stream(prompt: str, history: Sequence[ChatMessage] | None = None) -> AsyncGenerator[str, None]:
    """Mock implementation that raises an error"""
    raise Exception("Test error")
    yield  # Never reached, but needed for type checking


@pytest.mark.asyncio
async def test_error_handling(ai_service):
    # Test error handling
    ai_service.adapter.stream_response = error_stream

    with pytest.raises(Exception, match="Test error"):
        async for _ in ai_service.stream_chat_response("test"):
            pass  # We should never get here


@pytest.mark.asyncio
async def test_empty_history(ai_service):
    # Test with no history
    message = "Test message"

    tokens = []
    async for token in ai_service.stream_chat_response(message):
        tokens.append(token)

    assert tokens == ["Hello", " World", "!"]


@pytest.mark.asyncio
async def test_structured_response_validation(ai_service):
    # Test that structured responses are properly validated
    message = "Test message"

    responses = []
    async for response in ai_service.stream_structured_response(message, MockResponse):
        assert isinstance(response, MockResponse)
        assert hasattr(response, "answer")
        assert hasattr(response, "details")
        responses.append(response)

    assert len(responses) == 2
