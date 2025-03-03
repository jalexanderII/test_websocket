import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import WebSocket
from fastapi.testclient import TestClient

from app.api.handlers.websocket.connection_manager import ConnectionManager
from app.api.handlers.websocket.websocket_handler import WebSocketHandler
from app.schemas.chat import Chat
from app.schemas.websocket import CreateChatMessage, SendMessageRequest
from app.services.ai.pipelines.base import AIResponse
from app.services.chat.service import ChatService
from app.services.core.background_task_processor import TaskStatus
from app.utils.async_redis_utils.connection import AsyncConnectionManager
from app.utils.universal_serializer import safe_json_dumps

# Test data
TEST_USER_ID = 1
TEST_CHAT_ID = 1
TEST_MESSAGE = "Hello, world!"
TEST_TASK_ID = "test-task-id"

# Increase wait time for background tasks
TASK_WAIT_TIME = 0.5  # seconds


class TaskResult(TypedDict):
    status: Literal["completed", "failed", "pending"]
    result: dict
    error: str | None


@pytest.fixture
def test_client():
    from app.main import app
    return TestClient(app)


@pytest_asyncio.fixture
async def mock_redis_client():
    """Create a mock Redis client"""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=True)
    mock.sadd = AsyncMock(return_value=True)
    mock.srem = AsyncMock(return_value=True)
    mock.exists = AsyncMock(return_value=False)
    mock.close = AsyncMock()
    mock.info = AsyncMock(return_value={})
    return mock


@pytest_asyncio.fixture
async def mock_redis_manager(mock_redis_client):
    """Create a mock Redis connection manager"""
    mock = AsyncMock(spec=AsyncConnectionManager)
    mock.client = mock_redis_client
    mock.execute = AsyncMock(
        side_effect=lambda func_name, *args, **kwargs: getattr(mock_redis_client, func_name)(*args, **kwargs)
    )
    mock.health_check = AsyncMock(return_value={"status": "healthy"})
    return mock


@pytest_asyncio.fixture
async def mock_async_dict():
    """Create a mock AsyncDict"""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=True)
    mock.clear = AsyncMock(return_value=True)
    return mock


@pytest_asyncio.fixture
async def mock_async_set():
    """Create a mock AsyncSet"""
    mock = AsyncMock()
    mock.add = AsyncMock(return_value=True)
    mock.remove = AsyncMock(return_value=True)
    mock.clear = AsyncMock(return_value=True)
    mock.size = AsyncMock(return_value=0)
    return mock


@pytest_asyncio.fixture
async def connection_manager(mock_redis_manager, mock_async_dict, mock_async_set):
    """Create a connection manager with mocked Redis"""
    print("\n[DEBUG] Creating connection manager with mocked Redis")

    # Patch both AsyncDict and AsyncSet
    with (
        patch("app.api.handlers.websocket.connection_manager.AsyncDict", return_value=mock_async_dict),
        patch("app.api.handlers.websocket.connection_manager.AsyncSet", return_value=mock_async_set),
    ):
        manager = ConnectionManager(mock_redis_manager)
        print("[DEBUG] Connection manager created")
        yield manager
        print("[DEBUG] Cleaning up connection manager")
        await manager.close()
        print("[DEBUG] Connection manager cleanup complete")


@pytest_asyncio.fixture
async def mock_chat_service():
    return AsyncMock(spec=ChatService)


@pytest_asyncio.fixture
async def mock_websocket():
    """Create a mock websocket for testing"""
    mock = AsyncMock(spec=WebSocket)
    # Set up client info as a simple string instead of a mock
    mock.client = MagicMock()
    mock.client.host = "127.0.0.1"
    return mock


@pytest_asyncio.fixture(autouse=True)
async def mock_background_processor():
    """Mock background processor for testing"""
    with patch("app.api.handlers.websocket.websocket_handler.background_processor") as mock:
        # Mock add_task to execute the function immediately
        async def mock_add_task(func, *args, **kwargs):
            task_id = str(uuid.uuid4())
            print(f"\n[DEBUG] mock_add_task called with func: {func.__name__}, args: {args}, kwargs: {kwargs}")
            print(f"[DEBUG] Generated task_id: {task_id}")

            # Store task info for test access
            mock._last_task_id = task_id  # Always store the last task ID

            # Store task ID by function name for send_message test
            if func.__name__ == "_handle_user_message":
                mock._user_message_task_id = task_id
            elif func.__name__ == "_generate_standard_response":
                mock._ai_response_task_id = task_id

            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                print(f"[DEBUG] Function result type: {type(result)}")
                print(f"[DEBUG] Function result: {result}")

                # If result is already a dict, use it directly
                if isinstance(result, dict):
                    task_result = result
                    print(f"[DEBUG] Using dict result directly: {task_result}")
                # If result has model_dump method, use that
                elif hasattr(result, "model_dump"):
                    task_result = result.model_dump()
                    print(f"[DEBUG] Used model_dump result: {task_result}")
                # Otherwise use the result as is
                else:
                    task_result = result
                    print(f"[DEBUG] Using raw result: {task_result}")

                mock._task_results[task_id] = {
                    "status": TaskStatus.COMPLETED,
                    "result": task_result,
                }
                print(f"[DEBUG] Stored task result for {task_id}: {mock._task_results[task_id]}")
            except Exception as e:
                print(f"[DEBUG] Error in mock_add_task: {str(e)}")
                mock._task_results[task_id] = {
                    "status": TaskStatus.FAILED,
                    "error": str(e),
                }
            return task_id

        # Mock get_task_result to return the stored result
        async def mock_get_task_result(task_id):
            print(f"\n[DEBUG] mock_get_task_result called with task_id: {task_id}")
            result = mock._task_results.get(task_id)
            print(f"[DEBUG] Retrieved task result: {result}")
            if not result:
                return {"status": TaskStatus.PENDING}
            return result

        mock.add_task = AsyncMock(side_effect=mock_add_task)
        mock.get_task_result = AsyncMock(side_effect=mock_get_task_result)
        mock._task_results = {}
        mock._last_task_id = None
        mock._user_message_task_id = None
        mock._ai_response_task_id = None
        yield mock



@pytest.mark.asyncio
async def test_websocket_heartbeat(connection_manager, mock_websocket):
    """Test websocket heartbeat functionality"""
    print("\n[DEBUG] Starting test_websocket_heartbeat")

    print("[DEBUG] Connecting websocket")
    await connection_manager.connect(mock_websocket, TEST_USER_ID)
    print("[DEBUG] Websocket connected")

    # Test initial connection is alive
    print("[DEBUG] Testing initial connection")
    is_alive = await connection_manager.is_connection_alive(mock_websocket)
    print(f"[DEBUG] Initial connection alive status: {is_alive}")
    assert is_alive

    # Update heartbeat
    print("[DEBUG] Updating heartbeat")
    await connection_manager.update_heartbeat(mock_websocket)
    is_alive = await connection_manager.is_connection_alive(mock_websocket)
    print(f"[DEBUG] Connection alive status after update: {is_alive}")
    assert is_alive

    # Test with expired timeout
    print("[DEBUG] Testing expired timeout")
    with patch("app.api.handlers.websocket.connection_manager.datetime") as mock_datetime:
        mock_now = datetime.now(UTC)
        future_time = mock_now + timedelta(minutes=10)
        print(f"[DEBUG] Setting mock time to: {future_time}")
        mock_datetime.now.return_value = future_time
        mock_datetime.now.side_effect = lambda tz=None: future_time
        is_alive = await connection_manager.is_connection_alive(mock_websocket)
        print(f"[DEBUG] Connection alive status after timeout: {is_alive}")
        assert not is_alive
    print("[DEBUG] Test complete")


@pytest.mark.asyncio
async def test_websocket_broadcast(connection_manager, mock_websocket):
    """Test broadcasting messages to users"""
    await connection_manager.connect(mock_websocket, TEST_USER_ID)
    test_message = "Test broadcast message"

    await connection_manager.broadcast_to_user(TEST_USER_ID, test_message)
    mock_websocket.send_text.assert_called_once_with(test_message)


@pytest.mark.asyncio
async def test_websocket_handler_send_message(
    mock_websocket, mock_chat_service, connection_manager, mock_background_processor
):
    """Test sending messages through websocket handler"""
    handler = WebSocketHandler(mock_websocket, TEST_USER_ID, mock_chat_service, connection_manager)

    # Mock chat service responses
    mock_chat = MagicMock()
    mock_chat.id = TEST_CHAT_ID
    mock_chat_service.get_chat.return_value = mock_chat

    # Mock message response
    mock_message_data = {
        "id": 1,
        "content": TEST_MESSAGE,
        "is_ai": False,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    print(f"\n[DEBUG] Created mock_message_data: {mock_message_data}")

    mock_message = MagicMock()
    mock_message.id = mock_message_data["id"]
    mock_message.content = mock_message_data["content"]
    mock_message.is_ai = mock_message_data["is_ai"]
    mock_message.timestamp = datetime.fromisoformat(mock_message_data["timestamp"])
    mock_message.model_dump.return_value = mock_message_data
    mock_chat_service.send_message.return_value = mock_message
    print(f"[DEBUG] Set up mock_message with model_dump: {mock_message.model_dump()}")

    # Mock pipeline response
    with patch("app.services.ai.pipelines.manager.PipelineManager.get_pipeline") as mock_get_pipeline:

        class MockPipeline:
            async def execute(self, *args, **kwargs):
                yield AIResponse(content="Test response", response_type="stream")

        mock_get_pipeline.return_value = MockPipeline()

        # Test message handling
        request_data = SendMessageRequest(
            action="send_message", chat_id=TEST_CHAT_ID, content=TEST_MESSAGE, response_model=False
        )
        print(f"[DEBUG] Created request_data: {request_data}")

        # Connect the websocket
        await connection_manager.connect(mock_websocket, TEST_USER_ID)

        # Send the message
        print("\n[DEBUG] About to call handle_send_message")
        await handler.handle_send_message(request_data)

        # Wait for background tasks
        print("[DEBUG] Waiting for background tasks")
        await asyncio.sleep(TASK_WAIT_TIME)

        # Verify chat service was called
        mock_chat_service.get_chat.assert_called_once_with(TEST_CHAT_ID)
        assert mock_chat_service.send_message.call_count == 2  # User message and AI response


@pytest.mark.asyncio
async def test_websocket_handler_create_chat(
    mock_websocket, mock_chat_service, connection_manager, mock_background_processor
):
    """Test creating a new chat through websocket handler"""
    handler = WebSocketHandler(mock_websocket, TEST_USER_ID, mock_chat_service, connection_manager)

    # Mock chat service response
    chat_data = {"id": TEST_CHAT_ID, "user_id": TEST_USER_ID}
    mock_chat = MagicMock(spec=Chat)
    mock_chat.id = chat_data["id"]
    mock_chat.user_id = chat_data["user_id"]
    mock_chat.model_dump.return_value = chat_data
    mock_chat_service.create_chat.return_value = mock_chat

    # Connect the websocket
    await connection_manager.connect(mock_websocket, TEST_USER_ID)

    # Create message data
    message_data = CreateChatMessage(action="create_chat", user_id=TEST_USER_ID)

    # Create chat
    await handler.handle_create_chat(message_data)

    # Wait for background tasks
    await asyncio.sleep(TASK_WAIT_TIME)

    # Verify chat service was called
    mock_chat_service.create_chat.assert_called_once_with(TEST_USER_ID)

    # Verify task completion using the last task ID
    task_result: TaskResult = await mock_background_processor.get_task_result(mock_background_processor._last_task_id)
    assert task_result["status"] == TaskStatus.COMPLETED
    assert task_result["result"]["id"] == TEST_CHAT_ID
    assert task_result["result"]["user_id"] == TEST_USER_ID


@pytest.mark.asyncio
async def test_websocket_handler_join_chat(
    mock_websocket, mock_chat_service, connection_manager, mock_background_processor
):
    """Test joining an existing chat through websocket handler"""
    handler = WebSocketHandler(mock_websocket, TEST_USER_ID, mock_chat_service, connection_manager)

    # Mock chat service response
    chat_data = {"id": TEST_CHAT_ID, "user_id": TEST_USER_ID}
    mock_chat = MagicMock()
    mock_chat.id = chat_data["id"]
    mock_chat.user_id = chat_data["user_id"]
    mock_chat.model_dump.return_value = chat_data
    mock_chat_service.get_chat.return_value = mock_chat

    # Connect the websocket
    await connection_manager.connect(mock_websocket, TEST_USER_ID)

    message_data = MagicMock()
    message_data.chat_id = TEST_CHAT_ID

    # Join chat
    await handler.handle_join_chat(message_data)

    # Wait for background tasks
    await asyncio.sleep(TASK_WAIT_TIME)

    # Verify chat service was called
    mock_chat_service.get_chat.assert_called_once_with(TEST_CHAT_ID)

    # Verify task completion using the last task ID
    task_result: TaskResult = await mock_background_processor.get_task_result(mock_background_processor._last_task_id)
    assert task_result["status"] == TaskStatus.COMPLETED
    assert task_result["result"]["id"] == TEST_CHAT_ID
    assert task_result["result"]["user_id"] == TEST_USER_ID


@pytest.mark.asyncio
async def test_websocket_handler_structured_response(
    mock_websocket, mock_chat_service, connection_manager, mock_background_processor
):
    """Test handling structured AI responses"""
    handler = WebSocketHandler(mock_websocket, TEST_USER_ID, mock_chat_service, connection_manager)

    # Mock chat service
    mock_chat_service.get_chat.return_value = MagicMock(id=TEST_CHAT_ID)

    # Mock message response
    mock_message = MagicMock()
    mock_message.id = 1
    mock_message.content = TEST_MESSAGE
    mock_message.is_ai = False
    mock_message.timestamp = datetime.now(UTC)
    mock_message.model_dump.return_value = {
        "id": 1,
        "content": TEST_MESSAGE,
        "is_ai": False,
        "timestamp": mock_message.timestamp.isoformat(),
    }
    mock_chat_service.send_message.return_value = mock_message

    # Mock connection manager
    broadcast_mock = AsyncMock()
    connection_manager.broadcast_to_user = broadcast_mock

    # Mock pipeline response
    with patch("app.services.ai.pipelines.manager.PipelineManager.get_pipeline") as mock_get_pipeline:

        class MockPipeline:
            async def execute(self, *args, **kwargs):
                yield AIResponse(
                    content=safe_json_dumps({"answer": "Test answer", "reason": "Test reason"}),
                    response_type="structured",
                )

        mock_get_pipeline.return_value = MockPipeline()

        # Connect the websocket
        await connection_manager.connect(mock_websocket, TEST_USER_ID)

        # Send message with structured response
        message_data = SendMessageRequest(
            action="send_message", chat_id=TEST_CHAT_ID, content=TEST_MESSAGE, response_model=True
        )
        await handler.handle_send_message(message_data)

        # Wait for background tasks
        await asyncio.sleep(TASK_WAIT_TIME)

        # Verify messages were broadcast
        broadcast_calls = [json.loads(call.args[1]) for call in broadcast_mock.call_args_list]
        message_types = [msg["type"] for msg in broadcast_calls]

        assert "message" in message_types  # User message
        assert "structured_response" in message_types  # Structured response
        assert "generation_complete" in message_types  # Completion notification


@pytest.mark.asyncio
async def test_websocket_health(test_client, connection_manager):
    """Test websocket health endpoint"""
    # Create a mock health info response
    health_info = {
        "status": "healthy",
        "active_users_count": 0,
        "total_connections": 0,
        "dead_connections": 0,
        "connections_by_user": {},
        "redis_health": {"status": "healthy"},
        "last_heartbeat_stats": {
            "oldest_heartbeat": None,
            "newest_heartbeat": None,
            "total_tracked_heartbeats": 0,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Mock the manager's get_health_info method
    with patch("app.api.routes.websocket.manager") as mock_manager:
        mock_manager.get_health_info = AsyncMock(return_value=health_info)

        response = test_client.get("/api/ws/health")
        assert response.status_code == 200

        health_data = response.json()
        assert "status" in health_data
        assert "active_users_count" in health_data
        assert "total_connections" in health_data
        assert "redis_health" in health_data


@pytest.mark.asyncio
async def test_failed_task_handling(mock_websocket, mock_chat_service, connection_manager, mock_background_processor):
    """Test handling of failed background tasks"""
    handler = WebSocketHandler(mock_websocket, TEST_USER_ID, mock_chat_service, connection_manager)

    # Mock chat service to raise an error
    mock_chat_service.create_chat.side_effect = ValueError("Test error")

    # Connect the websocket
    await connection_manager.connect(mock_websocket, TEST_USER_ID)

    # Create message data
    message_data = CreateChatMessage(action="create_chat", user_id=TEST_USER_ID)
    await handler.handle_create_chat(message_data)

    # Wait for background tasks
    await asyncio.sleep(TASK_WAIT_TIME)

    # Verify chat service was called
    mock_chat_service.create_chat.assert_called_once_with(TEST_USER_ID)

    # Verify task failure using the last task ID
    task_result = await mock_background_processor.get_task_result(mock_background_processor._last_task_id)
    assert task_result["status"] == TaskStatus.FAILED  # type: ignore
    assert "Test error" in task_result["error"]  # type: ignore
