from datetime import UTC, datetime
from typing import List, Tuple

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.db.models import ChatDB, MessageDB, UserDB
from app.schemas.chat import Chat, Message, MessageCreate


class ChatRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_user(self, user_id: int) -> UserDB:
        user = self.db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            user = UserDB(
                id=user_id,
                username=f"user_{user_id}",
                email=f"user_{user_id}@example.com",
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        return user

    def create_chat(self, user_id: int) -> Chat:
        # Ensure user exists
        self.get_or_create_user(user_id)

        # Create new chat
        db_chat = ChatDB(user_id=user_id)
        self.db.add(db_chat)
        self.db.commit()
        self.db.refresh(db_chat)

        return Chat.model_validate(db_chat)

    def get_chat(self, chat_id: int) -> Chat | None:
        db_chat = self.db.query(ChatDB).filter(ChatDB.id == chat_id).first()
        if not db_chat:
            return None
        return Chat.model_validate(db_chat)

    def get_user_chats(self, user_id: int) -> List[Chat]:
        db_chats = self.db.query(ChatDB).filter(ChatDB.user_id == user_id).all()
        return [Chat.model_validate(chat) for chat in db_chats]

    def get_chat_messages(self, chat_id: int) -> List[Message]:
        messages = self.db.query(MessageDB).filter(MessageDB.chat_id == chat_id).all()
        return [Message.model_validate(msg) for msg in messages]

    def create_message(self, message: MessageCreate, task_id: str | None = None) -> Message:
        db_message = MessageDB(
            chat_id=message.chat_id,
            content=message.content,
            is_ai=message.is_ai,
            timestamp=datetime.now(UTC),
            task_id=task_id,
        )
        self.db.add(db_message)
        self.db.commit()
        self.db.refresh(db_message)
        return Message.model_validate(db_message)

    def update_message_content(self, message_id: int, content: str) -> None:
        self.db.execute(update(MessageDB).where(MessageDB.id == message_id).values(content=content))
        self.db.commit()

    def delete_chats(self, chat_ids: List[int]) -> Tuple[int, int]:
        """Delete multiple chats by their IDs. Returns tuple of (deleted_chats, deleted_messages)"""
        if not chat_ids:
            return (0, 0)

        try:
            # Delete messages first due to foreign key constraint
            deleted_messages = (
                self.db.query(MessageDB).filter(MessageDB.chat_id.in_(chat_ids)).delete(synchronize_session=False)
            )

            deleted_chats = self.db.query(ChatDB).filter(ChatDB.id.in_(chat_ids)).delete(synchronize_session=False)

            self.db.commit()
            return (deleted_chats, deleted_messages)

        except Exception:
            self.db.rollback()
            raise

    def get_empty_chat_ids(self, user_id: int) -> List[int]:
        """Get IDs of all empty chats for a user"""
        empty_chat_ids = (
            self.db.query(ChatDB.id)
            .outerjoin(MessageDB, ChatDB.id == MessageDB.chat_id)
            .filter(ChatDB.user_id == user_id)
            .group_by(ChatDB.id)
            .having(func.count(MessageDB.id) == 0)
            .all()
        )
        return [chat_id for (chat_id,) in empty_chat_ids]

    def update_chat_title(self, chat_id: int, title: str) -> None:
        """Update the title of a chat"""
        self.db.execute(update(ChatDB).where(ChatDB.id == chat_id).values(title=title))
        self.db.commit()
