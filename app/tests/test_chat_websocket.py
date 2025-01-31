import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

from app.api.routes.chat_websocket import ConnectionManager, CreateChatMessage, SendMessageRequest, WebSocketHandler
from app.schemas.chat import MessageCreate
from app.services.chat_service import ChatService

# Test data
TEST_USER_ID = 1
TEST_CHAT_ID = 1
TEST_MESSAGE = "Hello, world!"
TEST_TASK_ID = "test-task-id"


@pytest.fixture
def test_client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def connection_manager():
    return ConnectionManager()


@pytest.fixture
def mock_chat_service():
    return MagicMock(spec=ChatService)


@pytest.fixture
def mock_websocket():
    """Create a mock websocket for testing"""
    mock = AsyncMock(spec=WebSocket)
    # Set up client info as a simple string instead of a mock
    mock.client = MagicMock()
    mock.client.host = "127.0.0.1"
    return mock


@pytest.mark.asyncio
async def test_websocket_connection(connection_manager, mock_websocket):
    """Test websocket connection and disconnection"""
    # Test connection
    await connection_manager.connect(mock_websocket, TEST_USER_ID)
    assert TEST_USER_ID in connection_manager._connections
    assert mock_websocket in connection_manager._connections[TEST_USER_ID]
    assert mock_websocket in connection_manager._last_heartbeat

    # Test disconnection
    connection_manager.disconnect(mock_websocket, TEST_USER_ID)
    assert TEST_USER_ID not in connection_manager._connections
    assert mock_websocket not in connection_manager._last_heartbeat


@pytest.mark.asyncio
async def test_websocket_heartbeat(connection_manager, mock_websocket):
    """Test websocket heartbeat functionality"""
    await connection_manager.connect(mock_websocket, TEST_USER_ID)

    # Test initial connection is alive
    assert connection_manager.is_connection_alive(mock_websocket)

    # Update heartbeat
    connection_manager.update_heartbeat(mock_websocket)
    assert connection_manager.is_connection_alive(mock_websocket)

    # Test with expired timeout
    with patch("app.api.routes.chat_websocket.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime.fromtimestamp(9999999999, tz=timezone.utc)
        assert not connection_manager.is_connection_alive(mock_websocket)


@pytest.mark.asyncio
async def test_websocket_broadcast(connection_manager, mock_websocket):
    """Test broadcasting messages to users"""
    await connection_manager.connect(mock_websocket, TEST_USER_ID)
    test_message = "Test broadcast message"

    await connection_manager.broadcast_to_user(TEST_USER_ID, test_message)
    mock_websocket.send_text.assert_called_once_with(test_message)


@pytest.mark.asyncio
async def test_websocket_handler_send_message(mock_websocket, mock_chat_service, connection_manager):
    """Test sending messages through websocket handler"""
    handler = WebSocketHandler(mock_websocket, TEST_USER_ID, mock_chat_service, connection_manager)

    # Mock chat service response
    mock_message = MagicMock()
    mock_message.id = 1
    mock_message.content = TEST_MESSAGE
    mock_message.is_ai = False
    mock_message.timestamp = datetime.now(timezone.utc)
    mock_message.model_dump = MagicMock(
        return_value={"id": 1, "content": TEST_MESSAGE, "is_ai": False, "timestamp": mock_message.timestamp.isoformat()}
    )
    mock_chat_service.send_message.return_value = mock_message

    # Test message handling
    message_data = SendMessageRequest(
        action="send_message", chat_id=TEST_CHAT_ID, content=TEST_MESSAGE, response_model=False
    )

    await handler.handle_send_message(message_data)

    # Verify chat service was called
    mock_chat_service.send_message.assert_called_once()
    message_create = mock_chat_service.send_message.call_args[0][0]
    assert isinstance(message_create, MessageCreate)
    assert message_create.chat_id == TEST_CHAT_ID
    assert message_create.content == TEST_MESSAGE
    assert message_create.is_ai is False


@pytest.mark.asyncio
async def test_websocket_handler_create_chat(mock_websocket, mock_chat_service, connection_manager):
    """Test creating a new chat through websocket handler"""
    handler = WebSocketHandler(mock_websocket, TEST_USER_ID, mock_chat_service, connection_manager)

    # Mock chat service response
    mock_chat = MagicMock()
    mock_chat.id = TEST_CHAT_ID
    mock_chat_service.create_chat.return_value = mock_chat

    # Create message data
    message_data = CreateChatMessage(action="create_chat", user_id=TEST_USER_ID)
    await handler.handle_create_chat(message_data)

    # Verify chat service was called
    mock_chat_service.create_chat.assert_called_once_with(TEST_USER_ID)


@pytest.mark.asyncio
async def test_websocket_handler_join_chat(mock_websocket, mock_chat_service, connection_manager):
    """Test joining an existing chat through websocket handler"""
    handler = WebSocketHandler(mock_websocket, TEST_USER_ID, mock_chat_service, connection_manager)

    # Mock chat service response
    mock_chat = MagicMock()
    mock_chat.id = TEST_CHAT_ID
    mock_chat_service.get_chat.return_value = mock_chat

    message_data = MagicMock()
    message_data.chat_id = TEST_CHAT_ID

    await handler.handle_join_chat(message_data)

    # Verify chat service was called
    mock_chat_service.get_chat.assert_called_once_with(TEST_CHAT_ID)


@pytest.mark.asyncio
async def test_websocket_handler_structured_response(mock_websocket, mock_chat_service, connection_manager):
    """Test handling structured AI responses"""
    handler = WebSocketHandler(mock_websocket, TEST_USER_ID, mock_chat_service, connection_manager)

    # Mock structured response
    structured_response = {"answer": "Test answer", "reason": "Test reason"}

    async def mock_stream():
        yield structured_response

    mock_chat_service.stream_structured_ai_response.return_value = mock_stream()

    await handler._handle_structured_response(TEST_CHAT_ID, TEST_MESSAGE, TEST_TASK_ID)

    # Verify structured response was processed
    mock_chat_service.stream_structured_ai_response.assert_called_once()


@pytest.mark.asyncio
async def test_websocket_health(test_client):
    """Test websocket health endpoint"""
    response = test_client.get("/api/ws/health")
    assert response.status_code == 200

    health_data = response.json()
    assert "status" in health_data
    assert "active_users_count" in health_data
    assert "total_connections" in health_data
    assert "redis_health" in health_data
