from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Dict, Set
import json
import uuid

from infrastructure.db.database import get_db
from application.services.chat_service import ChatService


# Define response model at module level
class StrucResponse(BaseModel):
    answer: str
    reason: str


router = APIRouter()


# Store active connections
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


manager = ConnectionManager()


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket, user_id: int, db: Session = Depends(get_db)
):
    await manager.connect(websocket, user_id)
    chat_service = ChatService(db)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                action = message_data.get("action")

                if action == "send_message":
                    chat_id = message_data.get("chat_id")
                    content = message_data.get("content")
                    response_model = message_data.get("response_model")

                    # Save user message
                    message = await chat_service.send_message(chat_id, user_id, content)
                    await manager.broadcast_to_user(
                        user_id,
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

                    # Stream AI response
                    task_id = str(uuid.uuid4())

                    if response_model:
                        print(f"Streaming structured response for chat_id: {chat_id}")
                        async for chunk in chat_service.stream_structured_ai_response(
                            chat_id, user_id, content, response_model=StrucResponse
                        ):
                            await manager.broadcast_to_user(
                                user_id,
                                json.dumps(
                                    {
                                        "type": "structured_token",
                                        "data": chunk,
                                        "task_id": task_id,
                                    }
                                ),
                            )
                    else:
                        async for token in chat_service.stream_ai_response(
                            chat_id, user_id, content
                        ):
                            await manager.broadcast_to_user(
                                user_id,
                                json.dumps(
                                    {
                                        "type": "token",
                                        "token": token,
                                        "task_id": task_id,
                                    }
                                ),
                            )

                    # Send completion notification
                    await manager.broadcast_to_user(
                        user_id,
                        json.dumps({"type": "generation_complete", "task_id": task_id}),
                    )

                elif action == "create_chat":
                    # Create a new chat for the user
                    chat = chat_service.create_chat(user_id)
                    await manager.broadcast_to_user(
                        user_id,
                        json.dumps({"type": "chat_created", "chat_id": chat.id}),
                    )

                elif action == "join_chat":
                    # Join an existing chat
                    chat_id = message_data.get("chat_id")
                    chat = chat_service.get_chat(chat_id)
                    if not chat:
                        await websocket.send_text(
                            json.dumps({"type": "error", "message": "Chat not found"})
                        )
                    else:
                        await manager.broadcast_to_user(
                            user_id,
                            json.dumps({"type": "chat_joined", "chat_id": chat.id}),
                        )

            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Invalid JSON format"})
                )
            except Exception as e:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": str(e)})
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
