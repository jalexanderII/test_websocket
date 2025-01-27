from sqlalchemy import Column, Integer, DateTime, ForeignKey, String, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import List
from pydantic import BaseModel

from infrastructure.db.database import Base

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


class ChatDB(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = relationship("MessageDB", back_populates="chat")


class MessageDB(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    content = Column(String)
    is_ai = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    chat = relationship("ChatDB", back_populates="messages")
