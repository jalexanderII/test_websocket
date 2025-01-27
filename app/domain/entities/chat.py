from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    id: Optional[int] = None
    user_id: str
    content: str
    is_ai: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task_id: Optional[str] = None


class Chat(BaseModel):
    id: Optional[int] = None
    user_id: str
    title: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    messages: list[Message] = Field(default_factory=list)

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)
