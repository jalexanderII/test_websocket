from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict


class MessageBase(BaseModel):
    """Base class for message schemas"""

    content: str
    is_ai: bool


class MessageCreate(MessageBase):
    """Schema for creating a new message"""

    chat_id: int
    task_id: str | None = None


class Message(MessageBase):
    """Schema for a complete message"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    timestamp: datetime
    task_id: str | None = None


class ChatBase(BaseModel):
    """Base class for chat schemas"""

    title: str | None = None


class ChatCreate(ChatBase):
    """Schema for creating a new chat"""

    user_id: int


class Chat(ChatBase):
    """Schema for a complete chat"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    messages: List[Message] = []
