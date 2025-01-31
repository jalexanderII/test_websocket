from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )
    is_active = Column(Boolean, default=True)

    chats = relationship("ChatDB", back_populates="user", cascade="all, delete-orphan")


class ChatDB(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    messages = relationship("MessageDB", back_populates="chat", cascade="all, delete-orphan")
    user = relationship("UserDB", back_populates="chats")


class MessageDB(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text)
    is_ai = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))
    task_id = Column(String, nullable=True)

    chat = relationship("ChatDB", back_populates="messages")
    user = relationship("UserDB")
