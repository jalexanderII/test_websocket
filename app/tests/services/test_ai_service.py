from typing import AsyncGenerator, List, Optional
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.adapters.ai_adapter import ChatMessage
from app.services.ai_service import AIService


class MockResponse(BaseModel):
    """Test response model"""

    answer: str
    details: str


async def mock_stream_response(message: str, history: Optional[List[ChatMessage]] = None) -> AsyncGenerator[str, None]:
    tokens = ["Hello", " World", "!"]
    for token in tokens:
        yield token


async def mock_structured_stream(
    message: str, model: type[BaseModel], history: Optional[List[ChatMessage]] = None
) -> AsyncGenerator[MockResponse, None]:
    responses = [
        MockResponse(answer="First", details="Details 1"),
        MockResponse(answer="Second", details="Details 2"),
    ]
    for response in responses:
        yield response


async def error_stream(message: str, history: Optional[List[ChatMessage]] = None) -> AsyncGenerator[str, None]:
    if True:  # Always raise error
        raise Exception("Test error")
    yield ""  # Never reached, but needed for type checking


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.stream_response = mock_stream_response
    adapter.stream_structured_response = mock_structured_stream
    return adapter


@pytest.fixture
def ai_service(mock_adapter):
    return AIService(adapter=mock_adapter)


@pytest.mark.asyncio
async def test_stream_chat_response(ai_service, mock_adapter):
    # Test streaming chat response
    message = "Test message"
    history = [{"role": "user", "content": "Previous message"}]

    tokens = []
    async for token in ai_service.stream_chat_response(message, history=history):
        tokens.append(token)

    assert tokens == ["Hello", " World", "!"]


@pytest.mark.asyncio
async def test_stream_structured_response(ai_service, mock_adapter):
    # Test streaming structured response
    message = "Test message"
    history = [{"role": "user", "content": "Previous message"}]

    responses = []
    async for response in ai_service.stream_structured_response(message, MockResponse, history=history):
        responses.append(response)

    assert len(responses) == 2
    assert all(isinstance(r, MockResponse) for r in responses)
    assert [r.answer for r in responses] == ["First", "Second"]


@pytest.mark.asyncio
async def test_get_completion(ai_service, mock_adapter):
    # Test getting a complete response
    message = "Test message"
    history = [{"role": "user", "content": "Previous message"}]

    response = await ai_service.get_completion(message, history=history)

    assert response == "Hello World!"


@pytest.mark.asyncio
async def test_error_handling(ai_service, mock_adapter):
    # Test error handling
    ai_service.adapter.stream_response = error_stream

    with pytest.raises(Exception) as exc_info:
        async for _ in ai_service.stream_chat_response("test"):
            pass

    assert str(exc_info.value) == "Test error"
