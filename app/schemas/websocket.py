from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    TOKEN = "token"
    STRUCTURED_RESPONSE = "structured_response"
    ERROR = "error"
    CHAT_CREATED = "chat_created"
    CHAT_JOINED = "chat_joined"
    GENERATION_COMPLETE = "generation_complete"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    TASK_TIMEOUT = "task_timeout"


class WebSocketResponse(BaseModel):
    """Base model for all WebSocket responses"""

    type: MessageType
    task_id: str | None = None


class TokenResponse(WebSocketResponse):
    """Model for token stream responses"""

    type: MessageType = MessageType.TOKEN
    content: str
    chat_id: int


class ErrorResponse(WebSocketResponse):
    """Model for error responses"""

    type: MessageType = MessageType.ERROR
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class StructuredResponse(WebSocketResponse):
    """Model for structured responses"""

    type: MessageType = MessageType.STRUCTURED_RESPONSE
    content: Any
    chat_id: int
    metadata: dict[str, Any] | None = None


class TaskCompletedResponse(WebSocketResponse):
    """Model for task completion responses"""

    type: MessageType = MessageType.TASK_COMPLETED
    result: dict[str, Any]


class TaskFailedResponse(WebSocketResponse):
    """Model for task failure responses"""

    type: MessageType = MessageType.TASK_FAILED
    error: str


class ChatCreatedResponse(WebSocketResponse):
    """Model for chat creation responses"""

    type: MessageType = MessageType.CHAT_CREATED
    chat_id: int
    message: str | None = None


class ChatJoinedResponse(WebSocketResponse):
    """Model for chat join responses"""

    type: MessageType = MessageType.CHAT_JOINED
    chat_id: int


class WebSocketMessage(BaseModel):
    """Base class for all WebSocket messages"""

    action: str


class CreateChatMessage(WebSocketMessage):
    """Message for creating a new chat"""

    action: str = "create_chat"
    user_id: int
    initial_message: str | None = None
    response_model: bool = False
    pipeline_type: str | None = None


class SendMessageRequest(WebSocketMessage):
    """Message for sending a chat message"""

    action: str = "send_message"
    chat_id: int
    content: str
    pipeline_type: str | None = None
    response_model: bool = False


class JoinChatMessage(WebSocketMessage):
    """Message for joining an existing chat"""

    action: str = "join_chat"
    chat_id: int
