import json
from typing import AsyncGenerator, Optional, Sequence
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket

from app.api.handlers.websocket.connection_manager import ConnectionManager
from app.api.handlers.websocket.websocket_handler import WebSocketHandler
from app.schemas.websocket import SendMessageRequest
from app.services.ai.adapter import ChatMessage
from app.services.ai.pipelines.base import AIResponse
from app.services.chat.service import ChatService
from app.services.core.background_task_processor import TaskStatus
from app.utils.universal_serializer import safe_json_dumps


@pytest.fixture
def mock_websocket():
    return AsyncMock(spec=WebSocket)


@pytest.fixture
def mock_chat_service():
    service = AsyncMock(spec=ChatService)

    async def mock_get_chat(*args, **kwargs):
        return {"id": 1, "user_id": 1}

    async def mock_get_chat_history(*args, **kwargs):
        return [{"role": "user", "content": "previous message"}]

    async def mock_send_message(*args, **kwargs):
        return {"id": 1, "content": "test", "is_ai": False, "timestamp": "2024-01-01T00:00:00Z"}

    service.get_chat.side_effect = mock_get_chat
    service.get_chat_history.side_effect = mock_get_chat_history
    service.send_message.side_effect = mock_send_message

    return service


@pytest.fixture
def mock_connection_manager():
    return AsyncMock(spec=ConnectionManager)


@pytest.fixture
def mock_background_processor():
    processor = AsyncMock()

    async def mock_add_task(func, *args, **kwargs):
        # Execute the task function immediately for testing
        result = await func(*args, **kwargs)
        return "test_task_id"

    async def mock_get_task_result(*args, **kwargs):
        return {"status": TaskStatus.COMPLETED, "result": {"content": "test response"}}

    processor.add_task.side_effect = mock_add_task
    processor.get_task_result.side_effect = mock_get_task_result
    return processor


@pytest.fixture
def handler(mock_websocket, mock_chat_service, mock_connection_manager):
    return WebSocketHandler(
        websocket=mock_websocket,
        user_id=1,
        chat_service=mock_chat_service,
        connection_manager=mock_connection_manager,
    )


class MockPipeline:
    async def execute(
        self, message: str, history: Optional[Sequence[ChatMessage]] = None
    ) -> AsyncGenerator[AIResponse, None]:
        # Simulate a multi-step pipeline
        # Step 1: Stream some tokens
        yield AIResponse(content="First", response_type="stream")
        yield AIResponse(content="Response", response_type="stream")

        # Step 2: Send structured data
        yield AIResponse(content=safe_json_dumps({"step": "planning", "details": "test"}), response_type="structured")

        # Step 3: Final stream
        yield AIResponse(content="Final response", response_type="stream")


@pytest.mark.asyncio
async def test_handle_send_message(handler, mock_connection_manager, mock_chat_service, mock_background_processor):
    # Mock the pipeline and background processor
    with (
        patch("app.pipelines.manager.PipelineManager.get_pipeline") as mock_get_pipeline,
        patch("app.api.handlers.websocket_handler.background_processor", mock_background_processor),
    ):
        mock_get_pipeline.return_value = MockPipeline()

        # Create test message
        message = SendMessageRequest(chat_id=1, content="test message", pipeline_type="planning")

        # Handle message
        await handler.handle_send_message(message)

        # Verify chat service calls
        assert mock_chat_service.get_chat.call_count == 1
        assert mock_chat_service.get_chat_history.call_count == 1
        assert mock_chat_service.send_message.call_count >= 1

        # Verify background processor was used
        assert mock_background_processor.add_task.call_count == 1
        assert mock_background_processor.get_task_result.call_count >= 1

        # Verify messages were broadcast
        broadcast_calls = mock_connection_manager.broadcast_to_user.call_args_list

        # Should have multiple broadcasts:
        # 1. User message
        # 2. First stream token
        # 3. Second stream token
        # 4. Structured response
        # 5. Final stream token
        # 6. Generation complete
        # 7. Task completed notification
        assert len(broadcast_calls) >= 7

        # Verify message types
        messages = [json.loads(call.args[1]) for call in broadcast_calls]  # type: ignore

        message_types = [msg["type"] for msg in messages]
        assert "message" in message_types  # User message
        assert "token" in message_types  # Streaming tokens
        assert "structured_response" in message_types  # Structured response
        assert "generation_complete" in message_types  # Completion notification
        assert "task_completed" in message_types  # Task completion


@pytest.mark.asyncio
async def test_handle_send_message_chat_not_found(handler, mock_background_processor):
    with patch("app.api.handlers.websocket_handler.background_processor", mock_background_processor):
        # Mock chat service to return None for chat
        async def mock_get_chat(*args, **kwargs):
            return None

        handler.chat_service.get_chat.side_effect = mock_get_chat

        message = SendMessageRequest(chat_id=1, content="test message")

        # Handle message
        await handler.handle_send_message(message)

        # Verify error was sent
        handler.manager.broadcast_to_user.assert_called_once()
        error_message = json.loads(handler.manager.broadcast_to_user.call_args[0][1])  # type: ignore
        assert error_message["type"] == "error"
        assert "Chat not found" in error_message["message"]


@pytest.mark.asyncio
async def test_error_handling(handler, mock_connection_manager, mock_chat_service, mock_background_processor):
    # Mock the pipeline and background processor
    with (
        patch("app.pipelines.manager.PipelineManager.get_pipeline") as mock_get_pipeline,
        patch("app.api.handlers.websocket_handler.background_processor", mock_background_processor),
    ):
        # Configure pipeline to raise an error
        class ErrorPipeline:
            def execute(self, *args, **kwargs):
                async def generate():
                    raise ValueError("Test error")
                    yield  # This is never reached, but needed for type checking

                return generate()

        mock_get_pipeline.return_value = ErrorPipeline()

        # Create test message
        message = SendMessageRequest(chat_id=1, content="test message")

        # Handle message
        await handler.handle_send_message(message)

        # Verify error was broadcast
        mock_connection_manager.broadcast_to_user.assert_called_with(
            handler.user_id,
            safe_json_dumps({"type": "error", "message": "Test error"}),
        )
