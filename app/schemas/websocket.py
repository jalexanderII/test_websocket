# WebSocket message schemas
from pydantic import BaseModel


class WebSocketMessage(BaseModel):
    """Base class for all WebSocket messages"""

    action: str


class CreateChatMessage(WebSocketMessage):
    """Message for creating a new chat"""

    action: str = "create_chat"
    user_id: int
    initial_message: str | None = None
    response_model: bool = False


class SendMessageRequest(WebSocketMessage):
    """Message for sending a chat message"""

    action: str = "send_message"
    chat_id: int
    content: str
    response_model: bool = False


class JoinChatMessage(WebSocketMessage):
    """Message for joining an existing chat"""

    action: str = "join_chat"
    chat_id: int
