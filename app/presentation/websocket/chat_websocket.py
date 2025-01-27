from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from typing import Dict, Set
import json
import uuid

from infrastructure.db.database import get_db
from application.services.chat_service import ChatService
from application.task_manager import TaskManager

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

                    async def stream_wrapper():
                        async for token in chat_service.stream_ai_response(
                            chat_id, user_id, content
                        ):
                            await manager.broadcast_to_user(
                                user_id, json.dumps({"type": "token", "token": token})
                            )
                        # Send completion notification
                        await manager.broadcast_to_user(
                            user_id,
                            json.dumps(
                                {"type": "generation_complete", "task_id": task_id}
                            ),
                        )

                    stream_task = TaskManager.create_task(task_id, stream_wrapper())
                    try:
                        await stream_task
                    finally:
                        TaskManager.remove_task(task_id)

                elif action == "create_chat":
                    # Create a new chat for the user
                    chat = chat_service.create_chat(user_id)
                    await manager.broadcast_to_user(
                        user_id,
                        json.dumps({"type": "chat_created", "chat_id": chat.id}),
                    )

                elif action == "abort":
                    task_id = message_data.get("task_id")
                    if TaskManager.cancel_task(task_id):
                        await chat_service.abort_response(task_id)
                        await manager.broadcast_to_user(
                            user_id, json.dumps({"type": "aborted", "task_id": task_id})
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
