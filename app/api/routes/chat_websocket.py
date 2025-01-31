import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Set as PySet

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from redis_data_structures import Dict as RedisDict, Set
from sqlalchemy.orm import Session

from app.config.redis_config import redis_manager
from app.db.database import get_db
from app.schemas.chat import Message, MessageCreate
from app.schemas.websocket import CreateChatMessage, JoinChatMessage, SendMessageRequest
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


class WebSocketHandler:
    def __init__(
        self,
        websocket: WebSocket,
        user_id: int,
        chat_service: ChatService,
        # Dependency Injection: The handler explicitly declares its dependencies. vs accesing global instance
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
            # First verify the chat exists
            chat = self.chat_service.get_chat(message.chat_id)
            if not chat:
                raise ValueError("Chat not found")

            # Create and save user message synchronously
            message_create = MessageCreate(
                chat_id=message.chat_id,
                content=message.content,
                is_ai=False,
            )
            user_message = self.chat_service.send_message(message_create)

            # Broadcast the user message
            await self._broadcast_user_message(user_message)

            # Handle AI response
            if message.response_model:
                await self._handle_structured_response(
                    message.chat_id,
                    message.content,
                    task_id,
                )
            else:
                await self._handle_standard_response(
                    message.chat_id,
                    message.content,
                    task_id,
                )

            await self._broadcast_completion(task_id)
        except Exception as e:
            logger.exception("Error handling message")
            await self._send_error(str(e))

    async def handle_create_chat(self, message: CreateChatMessage):
        try:
            # Create chat synchronously
            chat = self.chat_service.create_chat(message.user_id)
            logger.info("Chat created successfully with id: %s", chat.id)

            # Send chat_created event
            await self.manager.broadcast_to_user(
                self.user_id,
                json.dumps(
                    {
                        "type": "chat_created",
                        "chat_id": chat.id,
                        "message": message.initial_message if message.initial_message else None,
                    }
                ),
            )

            # If there's an initial message, send it after chat creation
            if message.initial_message:
                # Create and save message synchronously
                message_create = MessageCreate(
                    chat_id=chat.id,
                    content=message.initial_message,
                    is_ai=False,
                )
                user_message = self.chat_service.send_message(message_create)

                # Broadcast the message
                await self._broadcast_user_message(user_message)

                # Handle AI response
                task_id = str(uuid.uuid4())
                if message.response_model:
                    await self._handle_structured_response(
                        chat.id,
                        message.initial_message,
                        task_id,
                    )
                else:
                    await self._handle_standard_response(
                        chat.id,
                        message.initial_message,
                        task_id,
                    )

                await self._broadcast_completion(task_id)

        except Exception as e:
            logger.exception("Error creating chat")
            await self._send_error(f"Failed to create chat: {str(e)}")

    async def handle_join_chat(self, message: JoinChatMessage):
        chat = self.chat_service.get_chat(message.chat_id)
        if not chat:
            await self._send_error("Chat not found")
        else:
            await self.manager.broadcast_to_user(self.user_id, json.dumps({"type": "chat_joined", "chat_id": chat.id}))

    async def _broadcast_user_message(self, message: Message):
        await self.manager.broadcast_to_user(
            self.user_id,
            json.dumps({"type": "message", "message": message.model_dump(mode="json")}),
        )

    async def _send_error(self, message: str):
        await self.websocket.send_text(json.dumps({"type": "error", "message": message}))

    async def _broadcast_completion(self, task_id: str):
        await self.manager.broadcast_to_user(
            self.user_id, json.dumps({"type": "generation_complete", "task_id": task_id})
        )

    async def _handle_structured_response(
        self,
        chat_id: int,
        content: str,
        task_id: str,
    ):
        try:
            async for response in self.chat_service.stream_structured_ai_response(
                chat_id,
                content,
            ):
                await self.manager.broadcast_to_user(
                    self.user_id,
                    json.dumps(
                        {
                            "type": "structured_token",
                            "data": response.model_dump(),
                            "task_id": task_id,
                        }
                    ),
                )
        except Exception as e:
            logger.exception("Error streaming structured response")
            await self._send_error(str(e))

    async def _handle_standard_response(
        self,
        chat_id: int,
        content: str,
        task_id: str,
    ):
        try:
            async for token in self.chat_service.stream_ai_response(chat_id, content):
                await self.manager.broadcast_to_user(
                    self.user_id,
                    json.dumps(
                        {
                            "type": "token",
                            "content": token,
                            "task_id": task_id,
                        }
                    ),
                )
        except Exception as e:
            logger.exception("Error streaming response")
            await self._send_error(str(e))


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
