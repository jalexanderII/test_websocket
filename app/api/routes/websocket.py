from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.handlers.websocket.connection_manager import ConnectionManager
from app.api.handlers.websocket.websocket_handler import WebSocketHandler
from app.config.database import get_db
from app.config.logger import get_logger
from app.services.chat.service import ChatService

logger = get_logger(__name__)


ws_router = APIRouter()
manager = ConnectionManager()


@ws_router.websocket("/ws/{user_id}")
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


@ws_router.get("/ws/health")
async def websocket_health():
    """Health check endpoint for WebSocket service with detailed metrics"""
    return manager.get_health_info()
