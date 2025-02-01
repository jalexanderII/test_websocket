# type: ignore[misc]
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore[attr-defined]

from app.config.database import Base


class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    chats: Mapped[list["ChatDB"]] = relationship(
        "ChatDB",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",  # Always load chats with user
    )


class ChatDB(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user: Mapped["UserDB"] = relationship("UserDB", back_populates="chats", lazy="selectin")
    messages: Mapped[list["MessageDB"]] = relationship(
        "MessageDB",
        back_populates="chat",
        cascade="all, delete-orphan",
        lazy="selectin",  # Always load messages with chat
        order_by="MessageDB.timestamp",  # Keep messages ordered by timestamp
    )


class MessageDB(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chat_id: Mapped[int] = mapped_column(Integer, ForeignKey("chats.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    task_id: Mapped[str | None] = mapped_column(String, nullable=True)

    chat: Mapped["ChatDB"] = relationship("ChatDB", back_populates="messages", lazy="selectin")
