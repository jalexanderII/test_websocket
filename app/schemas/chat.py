from datetime import datetime
from typing import List
from pydantic import BaseModel


class Message(BaseModel):
    id: int
    chat_id: int
    content: str
    is_ai: bool
    timestamp: datetime

    class Config:
        from_attributes = True


class Chat(BaseModel):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    messages: List[Message] = []

    class Config:
        from_attributes = True
