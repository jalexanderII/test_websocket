import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Set as PySet

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from redis_data_structures import Dict as RedisDict, Set
from sqlalchemy.orm import Session

from app.config.redis_config import redis_manager
from app.db.database import get_db
from app.schemas.chat import Message, MessageCreate
from app.schemas.websocket import CreateChatMessage, JoinChatMessage, SendMessageRequest
from app.services.background_task_processor import BackgroundTaskProcessor, TaskStatus
from app.services.chat_service import ChatService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebSocketConnection(BaseModel):
    """Model for storing websocket connection metadata"""

    user_id: int
    last_heartbeat: datetime
    client_info: dict
    connection_count: int


class ConnectionManager:
    def __init__(self):
        self.active_users: Set = Set("active_users", connection_manager=redis_manager)
        self.connection_metadata = RedisDict("connection_metadata", connection_manager=redis_manager)
        self._connections: Dict[int, PySet[WebSocket]] = {}
        self._last_heartbeat: Dict[WebSocket, float] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()

        # Add to active users set
        self.active_users.add(user_id)

        # Update connection metadata
        meta_key = f"user:{user_id}"
        existing_meta = self.connection_metadata.get(meta_key)

        # Get client info safely
        try:
            client_ip = websocket.client.host if websocket.client else "unknown"
        except Exception:
            client_ip = "unknown"

        client_info = {"ip": client_ip}

        if existing_meta:
            connection_meta = WebSocketConnection.model_validate(existing_meta)
            connection_meta.connection_count += 1
            connection_meta.last_heartbeat = datetime.now(timezone.utc)
            connection_meta.client_info.update(client_info)
        else:
            connection_meta = WebSocketConnection(
                user_id=user_id, last_heartbeat=datetime.now(timezone.utc), client_info=client_info, connection_count=1
            )

        # Store metadata in Redis
        self.connection_metadata[meta_key] = connection_meta.model_dump(mode="json")

        # Store WebSocket connection in memory
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)
        self._last_heartbeat[websocket] = datetime.now(timezone.utc).timestamp()

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)  # set.discard() is safe if element doesn't exist
            if websocket in self._last_heartbeat:
                del self._last_heartbeat[websocket]

            # Update connection metadata
            meta_key = f"user:{user_id}"
            if meta := self.connection_metadata.get(meta_key):
                connection_meta = WebSocketConnection.model_validate(meta)
                connection_meta.connection_count -= 1

                if connection_meta.connection_count <= 0:
                    # Use dict del instead of remove
                    del self.connection_metadata[meta_key]
                    self.active_users.remove(user_id)
                else:
                    # Update metadata with decremented count
                    self.connection_metadata[meta_key] = connection_meta.model_dump()

            if not self._connections[user_id]:
                del self._connections[user_id]

    async def broadcast_to_user(self, user_id: int, message: str):
        if user_id in self._connections:
            # Convert to list to fix iteration typing issue
            connections = list(self._connections[user_id])
            for connection in connections:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.exception("Failed to send message to user %s: %s", user_id, str(e))
                    await self.handle_failed_connection(connection, user_id)

    async def handle_failed_connection(self, websocket: WebSocket, user_id: int):
        """Handle cleanup of failed connections"""
        self.disconnect(websocket, user_id)

    def update_heartbeat(self, websocket: WebSocket):
        """Update last heartbeat time for a connection"""
        self._last_heartbeat[websocket] = datetime.now(timezone.utc).timestamp()

    def is_connection_alive(self, websocket: WebSocket, timeout_seconds: int = 30) -> bool:
        """Check if a connection is still alive based on its last heartbeat"""
        if websocket not in self._last_heartbeat:
            return False
        last_heartbeat = self._last_heartbeat[websocket]
        current_time = datetime.now(timezone.utc).timestamp()
        return (current_time - last_heartbeat) < timeout_seconds

    def get_health_info(self) -> dict:
        """Get detailed health information about WebSocket connections"""
        current_time = datetime.now(timezone.utc).timestamp()
        # Fix sum() and len() typing issues by converting to list
        active_connections = sum(len(list(connections)) for connections in self._connections.values())
        dead_connections = sum(1 for ws in self._last_heartbeat if (current_time - self._last_heartbeat[ws]) >= 30)

        return {
            "status": "healthy" if active_connections > 0 and dead_connections == 0 else "degraded",
            "active_users_count": self.active_users.size(),
            "total_connections": active_connections,
            "dead_connections": dead_connections,
            "connections_by_user": {
                user_id: len(list(connections)) for user_id, connections in self._connections.items()
            },
            "redis_health": redis_manager.health_check(),
            "last_heartbeat_stats": {
                "oldest_heartbeat": min(self._last_heartbeat.values()) if self._last_heartbeat else None,
                "newest_heartbeat": max(self._last_heartbeat.values()) if self._last_heartbeat else None,
                "total_tracked_heartbeats": len(self._last_heartbeat),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Initialize background task processor
background_processor = BackgroundTaskProcessor(max_workers=5)


class WebSocketHandler:
    def __init__(
        self,
        websocket: WebSocket,
        user_id: int,
        chat_service: ChatService,
        connection_manager: ConnectionManager,
    ):
        self.websocket = websocket
        self.user_id = user_id
        self.chat_service = chat_service
        self.manager = connection_manager

    async def handle_message(self, data: str) -> None:
        """Handle incoming WebSocket messages"""
        try:
            message_dict = json.loads(data)
            action = message_dict.get("action")

            match action:
                case "create_chat":
                    message = CreateChatMessage(**message_dict)
                    await self.handle_create_chat(message)
                case "send_message":
                    message = SendMessageRequest(**message_dict)
                    await self.handle_send_message(message)
                case "join_chat":
                    message = JoinChatMessage(**message_dict)
                    await self.handle_join_chat(message)
                case _:
                    await self._send_error(f"Unknown action: {action}")

        except ValidationError as e:
            logger.error("Message validation error: %s", str(e))
            await self._send_error(str(e))
        except Exception as e:
            logger.exception("Error handling message")
            await self._send_error(str(e))

    async def handle_send_message(self, message: SendMessageRequest):
        task_id = str(uuid.uuid4())

        try:
            # First verify the chat exists and create user message in background
            task_id = await background_processor.add_task(
                self._handle_user_message,
                message.chat_id,
                message.content,
            )

            # Send task started notification
            await self.manager.broadcast_to_user(
                self.user_id,
                json.dumps(
                    {
                        "type": "task_started",
                        "task_id": task_id,
                        "message": "Message processing started",
                    }
                ),
            )

            # Start task monitoring
            await self._monitor_task(task_id)

            # Start AI response generation if requested
            if message.response_model:
                ai_task_id = await background_processor.add_task(
                    self._generate_structured_response,
                    chat_id=message.chat_id,
                    user_message=message.content,
                )
            else:
                ai_task_id = await background_processor.add_task(
                    self._generate_standard_response,
                    chat_id=message.chat_id,
                    user_message=message.content,
                )

            # Monitor AI response generation
            await self._monitor_task(ai_task_id)

        except Exception as e:
            logger.exception("Error handling message")
            await self._send_error(str(e))

    async def _handle_user_message(self, chat_id: int, content: str) -> Dict[str, Any]:
        """Handle sending and broadcasting a user message"""
        # Verify chat exists
        chat = await self.chat_service.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        # Create and save user message
        message_create = MessageCreate(
            chat_id=chat_id,
            content=content,
            is_ai=False,
        )
        user_message = await self.chat_service.send_message(message_create)

        # Broadcast the user message
        await self._broadcast_user_message(user_message)

        # Return message data
        if hasattr(user_message, "model_dump"):
            return user_message.model_dump()
        elif isinstance(user_message, dict):
            return user_message
        else:
            # Fallback to manual attribute extraction for any other type
            return {
                "id": getattr(user_message, "id", None),
                "content": getattr(user_message, "content", ""),
                "is_ai": getattr(user_message, "is_ai", False),
                "timestamp": getattr(user_message, "timestamp", datetime.now(timezone.utc)).isoformat(),
            }

    async def _monitor_task(self, task_id: str) -> None:
        """Monitor a background task and send updates"""
        try:
            while True:
                # Wait for task to be ready
                await asyncio.sleep(0.1)

                task_data = await background_processor.get_task_result(task_id)
                if not task_data:
                    logger.error("Task %s not found", task_id)
                    await self._send_error(f"Task {task_id} not found")
                    break

                status = task_data.get("status")
                if not status:
                    logger.error("Task %s has no status", task_id)
                    break

                if status == TaskStatus.COMPLETED:
                    # Task completed successfully
                    result = task_data.get("result", {})
                    # Ensure result is JSON serializable
                    if hasattr(result, "model_dump"):
                        result = result.model_dump(mode="json")
                    await self.manager.broadcast_to_user(
                        self.user_id,
                        json.dumps(
                            {
                                "type": "task_completed",
                                "task_id": task_id,
                                "result": result,
                            }
                        ),
                    )
                    break
                elif status == TaskStatus.FAILED:
                    # Task failed
                    error = task_data.get("error", "Unknown error")
                    await self.manager.broadcast_to_user(
                        self.user_id,
                        json.dumps(
                            {
                                "type": "task_failed",
                                "task_id": task_id,
                                "error": str(error),
                            }
                        ),
                    )
                    break
                elif status == TaskStatus.CANCELLED:
                    # Task was cancelled
                    await self.manager.broadcast_to_user(
                        self.user_id,
                        json.dumps(
                            {
                                "type": "task_cancelled",
                                "task_id": task_id,
                            }
                        ),
                    )
                    break

                # Continue monitoring if task is still running
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.exception("Error monitoring task %s", task_id)
            await self._send_error(str(e))

    async def _generate_structured_response(self, chat_id: int, user_message: str) -> Dict:
        """Generate a structured AI response"""
        try:
            latest_response = None
            async for response in self.chat_service.stream_structured_ai_response(chat_id, user_message):
                latest_response = response
                # Send progress update
                await self.manager.broadcast_to_user(
                    self.user_id,
                    json.dumps(
                        {
                            "type": "structured_update",
                            "content": response if isinstance(response, dict) else response.model_dump(),
                        }
                    ),
                )
            return (
                latest_response
                if isinstance(latest_response, dict)
                else latest_response.model_dump()
                if latest_response
                else {}
            )
        except Exception:
            logger.exception("Error generating structured response")
            raise

    async def _generate_standard_response(self, chat_id: int, user_message: str) -> Dict:
        """Generate a standard AI response"""
        try:
            complete_response = ""
            async for token in self.chat_service.stream_ai_response(chat_id, user_message):
                complete_response += token
                # Send progress update
                await self.manager.broadcast_to_user(
                    self.user_id,
                    json.dumps(
                        {
                            "type": "token",
                            "content": token,
                        }
                    ),
                )
            return {"content": complete_response}
        except Exception:
            logger.exception("Error generating standard response")
            raise

    async def handle_create_chat(self, message: CreateChatMessage):
        try:
            # Create chat in background
            task_id = await background_processor.add_task(self.chat_service.create_chat, message.user_id)

            # Wait for task completion with timeout
            max_retries = 10
            retry_count = 0
            while retry_count < max_retries:
                task_data = await background_processor.get_task_result(task_id)
                if not task_data:
                    await asyncio.sleep(0.1)
                    retry_count += 1
                    continue

                status = task_data.get("status")
                if status == TaskStatus.COMPLETED:
                    result = task_data.get("result")
                    if not isinstance(result, dict):
                        raise Exception("Invalid chat result")

                    chat_id = result.get("id")
                    if not chat_id:
                        raise Exception("Chat result missing ID")

                    logger.info("Chat created successfully with id: %s", chat_id)

                    # Send chat_created event
                    await self.manager.broadcast_to_user(
                        self.user_id,
                        json.dumps(
                            {
                                "type": "chat_created",
                                "chat_id": chat_id,
                                "message": message.initial_message if message.initial_message else None,
                            }
                        ),
                    )

                    # If there's an initial message, send it and get AI response
                    if message.initial_message:
                        # Send initial message
                        message_task_id = await background_processor.add_task(
                            self._handle_initial_message, chat_id, message.initial_message
                        )
                        await self._monitor_task(message_task_id)

                        # Generate AI response
                        ai_task_id = await background_processor.add_task(
                            self._generate_standard_response,
                            chat_id=chat_id,
                            user_message=message.initial_message,
                        )
                        await self._monitor_task(ai_task_id)
                    return

                elif status in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    error = task_data.get("error", "Unknown error")
                    raise Exception(f"Failed to create chat: {error}")

                await asyncio.sleep(0.1)
                retry_count += 1

            raise Exception("Timeout waiting for chat creation")

        except Exception as e:
            logger.exception("Error creating chat")
            await self._send_error(str(e))

    async def _handle_initial_message(self, chat_id: int, content: str) -> None:
        """Handle sending the initial message in a new chat"""
        message_create = MessageCreate(
            chat_id=chat_id,
            content=content,
            is_ai=False,
        )
        message = await self.chat_service.send_message(message_create)
        await self._broadcast_user_message(message)

    async def handle_join_chat(self, message: JoinChatMessage):
        try:
            # Verify chat exists in background
            task_id = await background_processor.add_task(self.chat_service.get_chat, message.chat_id)

            task_data = await background_processor.get_task_result(task_id)
            if not task_data:
                raise Exception("Failed to join chat: Task not found")

            status = task_data.get("status")
            if status == TaskStatus.COMPLETED:
                result = task_data.get("result")
                if not result:
                    raise ValueError("Chat not found")

                await self.manager.broadcast_to_user(
                    self.user_id,
                    json.dumps(
                        {
                            "type": "chat_joined",
                            "chat_id": message.chat_id,
                        }
                    ),
                )
            else:
                error = task_data.get("error", "Unknown error")
                raise Exception(f"Failed to join chat: {error}")

        except Exception as e:
            logger.exception("Error joining chat")
            await self._send_error(str(e))

    async def _broadcast_user_message(self, message: Message) -> None:
        """Broadcast a user message to all connected clients"""
        try:
            # Ensure message is JSON serializable
            message_data = message.model_dump(mode="json") if hasattr(message, "model_dump") else message
            await self.manager.broadcast_to_user(
                self.user_id,
                json.dumps({"type": "message", "message": message_data}),
            )
        except Exception:
            logger.exception("Error broadcasting user message")
            raise

    async def _send_error(self, error: str) -> None:
        """Send an error message to the client"""
        try:
            await self.manager.broadcast_to_user(
                self.user_id,
                json.dumps({"type": "error", "message": error}),
            )
        except Exception:
            logger.exception("Error sending error message")
            # If we can't send the error, just log it
            pass


router = APIRouter()
manager = ConnectionManager()


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, db: Session = Depends(get_db)):
    logger.info("New WebSocket connection request for user_id: %s", user_id)
    await manager.connect(websocket, user_id)

    # Each connection needs its own instances to maintain proper isolation and resource management
    # ChatService needs a database session (db) which should be connection-specific for proper transaction management
    chat_service = ChatService(db)
    # WebSocketHandler is created per connection because it handles the specific websocket instance and user_id for that connection
    handler = WebSocketHandler(websocket, user_id, chat_service, manager)
    logger.info("WebSocket connection established for user_id: %s", user_id)

    try:
        while True:
            message = await websocket.receive()
            message_type = message["type"]
            logger.info("Received message type: %s", message_type)

            if message_type == "websocket.disconnect":
                logger.info("WebSocket disconnect received for user_id: %s", user_id)
                break
            elif message_type == "websocket.ping":
                await websocket.send({"type": "websocket.pong"})
                manager.update_heartbeat(websocket)
            elif message_type == "websocket.receive":
                data = message.get("text")
                if not data:
                    logger.warning("Received empty message data")
                    continue

                logger.info("Processing WebSocket message: %s", data)
                await handler.handle_message(data)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for user_id: %s", user_id)
    except Exception as e:
        logger.exception("WebSocket error: %s", str(e))
    finally:
        logger.info("Cleaning up WebSocket connection for user_id: %s", user_id)
        manager.disconnect(websocket, user_id)


@router.get("/ws/health")
async def websocket_health():
    """Health check endpoint for WebSocket service with detailed metrics"""
    return manager.get_health_info()
