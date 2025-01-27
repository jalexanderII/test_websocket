from functools import partial
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Callable, Coroutine, Dict, Set, Any, Optional
import json
import uuid
from datetime import datetime, timezone

from infrastructure.db.database import get_db
from application.services.chat_service import ChatService


# Define response model at module level
class StrucResponse(BaseModel):
    answer: str
    reason: str


class MessageData(BaseModel):
    action: str
    chat_id: Optional[int] = None
    content: Optional[str] = None
    response_model: Optional[bool] = None

    @classmethod
    def from_ws_message(cls, message: str):
        message_dict = json.loads(message)
        return MessageData(
            action=message_dict["action"],
            chat_id=message_dict.get("chat_id"),
            content=message_dict.get("content"),
            response_model=bool(message_dict.get("response_model")),
        )


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def broadcast_to_user(self, user_id: int, message: str):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                await connection.send_text(message)


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

    async def _send_interim_message(self, content: str, task_id: str) -> None:
        """Send an interim message to the client."""
        await self.manager.broadcast_to_user(
            self.user_id,
            json.dumps(
                {
                    "type": "interim_message",
                    "message": {
                        "content": content,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "task_id": task_id,
                    },
                }
            ),
        )

    async def handle_send_message(self, message_data: MessageData):
        if not message_data.chat_id or not message_data.content:
            raise ValueError("chat_id and content are required for send_message")

        task_id = str(uuid.uuid4())

        # Create a bound version of _send_interim_message with task_id
        bound_interim_handler = partial(self._send_interim_message, task_id=task_id)

        # Save and broadcast user message
        message = await self.chat_service.send_message(
            message_data.chat_id,
            message_data.content,
        )
        await self._broadcast_user_message(message)

        # Handle AI response
        if message_data.response_model:
            await self._handle_structured_response(
                message_data.chat_id,
                message_data.content,
                task_id,
                bound_interim_handler,
            )
        else:
            await self._handle_standard_response(
                message_data.chat_id,
                message_data.content,
                task_id,
                bound_interim_handler,
            )

        # Send completion notification
        await self._broadcast_completion(task_id)

    async def handle_create_chat(self):
        chat = self.chat_service.create_chat(self.user_id)
        await self.manager.broadcast_to_user(
            self.user_id, json.dumps({"type": "chat_created", "chat_id": chat.id})
        )

    async def handle_join_chat(self, message_data: MessageData):
        if not message_data.chat_id:
            raise ValueError("chat_id is required for join_chat")

        chat = self.chat_service.get_chat(message_data.chat_id)

        if not chat:
            await self._send_error("Chat not found")
        else:
            await self.manager.broadcast_to_user(
                self.user_id, json.dumps({"type": "chat_joined", "chat_id": chat.id})
            )

    async def _broadcast_user_message(self, message: Any):
        await self.manager.broadcast_to_user(
            self.user_id,
            json.dumps(
                {
                    "type": "message",
                    "message": {
                        "id": message.id,
                        "content": message.content,
                        "is_ai": message.is_ai,
                        "timestamp": message.timestamp.isoformat(),
                    },
                }
            ),
        )

    async def _handle_structured_response(
        self,
        chat_id: int,
        content: str,
        task_id: str,
        bound_interim_handler: Callable[[str], Coroutine[Any, Any, None]],
    ):
        async for chunk in self.chat_service.stream_structured_ai_response(
            chat_id,
            content,
            response_model=StrucResponse,
            interim_message_handler=bound_interim_handler,
        ):
            print(chunk)
            await self.manager.broadcast_to_user(
                self.user_id,
                json.dumps(
                    {
                        "type": "structured_token",
                        "data": chunk,
                        "task_id": task_id,
                    }
                ),
            )

    async def _handle_standard_response(
        self,
        chat_id: int,
        content: str,
        task_id: str,
        bound_interim_handler: Callable[[str], Coroutine[Any, Any, None]],
    ):
        async for token in self.chat_service.stream_ai_response(
            chat_id,
            content,
            interim_message_handler=bound_interim_handler,
        ):
            await self.manager.broadcast_to_user(
                self.user_id,
                json.dumps(
                    {
                        "type": "token",
                        "token": token,
                        "task_id": task_id,
                    }
                ),
            )

    async def _broadcast_completion(self, task_id: str):
        await self.manager.broadcast_to_user(
            self.user_id,
            json.dumps({"type": "generation_complete", "task_id": task_id}),
        )

    async def _send_error(self, message: str):
        await self.websocket.send_text(
            json.dumps({"type": "error", "message": message})
        )


router = APIRouter()
manager = ConnectionManager()


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket, user_id: int, db: Session = Depends(get_db)
):
    await manager.connect(websocket, user_id)
    chat_service = ChatService(db)
    handler = WebSocketHandler(websocket, user_id, chat_service, manager)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message_data = MessageData.from_ws_message(data)

                if message_data.action == "send_message":
                    await handler.handle_send_message(message_data)
                elif message_data.action == "create_chat":
                    await handler.handle_create_chat()
                elif message_data.action == "join_chat":
                    await handler.handle_join_chat(message_data)

            except json.JSONDecodeError:
                await handler._send_error("Invalid JSON format")
            except Exception as e:
                await handler._send_error(str(e))

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
