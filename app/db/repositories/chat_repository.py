from typing import List, Optional, cast

from db.models import ChatDB, MessageDB
from schemas.chat import Chat, Message
from sqlalchemy import Column
from sqlalchemy.orm import Session


class ChatRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_chat(self, user_id: int) -> Chat:
        db_chat = ChatDB(user_id=user_id)
        self.db.add(db_chat)
        self.db.commit()
        self.db.refresh(db_chat)
        return Chat(
            id=db_chat.id,
            user_id=db_chat.user_id,
            created_at=db_chat.created_at,
            updated_at=db_chat.updated_at,
        )

    def get_chat(self, chat_id: int) -> Optional[Chat]:
        db_chat = self.db.query(ChatDB).filter(ChatDB.id == chat_id).first()
        if not db_chat:
            return None
        return Chat(
            id=db_chat.id,
            user_id=db_chat.user_id,
            created_at=db_chat.created_at,
            updated_at=db_chat.updated_at,
            messages=[
                Message(
                    id=msg.id,
                    chat_id=msg.user_id,
                    content=msg.content,
                    is_ai=msg.is_ai,
                    timestamp=msg.timestamp,
                )
                for msg in db_chat.messages
            ],
        )

    def add_message(self, chat_id: int, message: Message) -> Message:
        db_message = MessageDB(
            chat_id=chat_id,
            user_id=int(message.chat_id),
            content=message.content,
            is_ai=message.is_ai,
        )
        self.db.add(db_message)
        self.db.commit()
        self.db.refresh(db_message)
        return Message(
            id=db_message.id,
            chat_id=db_message.user_id,
            content=db_message.content,
            is_ai=db_message.is_ai,
            timestamp=db_message.timestamp,
        )

    def get_user_chats(self, user_id: int) -> List[Chat]:
        db_chats = self.db.query(ChatDB).filter(ChatDB.user_id == user_id).all()
        return [
            Chat(
                id=chat.id,
                user_id=chat.user_id,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
            )
            for chat in db_chats
        ]

    def get_chat_messages(self, chat_id: int) -> List[Message]:
        db_chat = self.db.query(ChatDB).filter(ChatDB.id == chat_id).first()
        if not db_chat:
            return []
        return [
            Message(
                id=msg.id,
                chat_id=msg.user_id,
                content=msg.content,
                is_ai=msg.is_ai,
                timestamp=msg.timestamp,
            )
            for msg in db_chat.messages
        ]

    def update_message(self, message: Message) -> Message:
        db_message = self.db.query(MessageDB).filter(MessageDB.id == message.id).first()
        if not db_message:
            raise ValueError(f"Message with id {message.id} not found")

        db_message.content = cast(Column[str], message.content)
        self.db.commit()
        self.db.refresh(db_message)

        return Message(
            id=db_message.id,
            chat_id=db_message.user_id,
            content=str(db_message.content),
            is_ai=db_message.is_ai,
            timestamp=db_message.timestamp,
        )
