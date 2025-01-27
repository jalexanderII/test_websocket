from typing import List, Optional
from sqlalchemy.orm import Session
from domain.entities.chat import Chat as ChatEntity, Message as MessageEntity
from infrastructure.db.models import Chat, Message


class ChatRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_chat(self, user_id: int) -> ChatEntity:
        db_chat = Chat(user_id=user_id)
        self.db.add(db_chat)
        self.db.commit()
        self.db.refresh(db_chat)
        return ChatEntity(
            id=db_chat.id,
            user_id=str(db_chat.user_id),
            title=db_chat.title,
            created_at=db_chat.created_at,
            updated_at=db_chat.updated_at,
        )

    def get_chat(self, chat_id: int) -> Optional[ChatEntity]:
        db_chat = self.db.query(Chat).filter(Chat.id == chat_id).first()
        if not db_chat:
            return None
        return ChatEntity(
            id=db_chat.id,
            user_id=str(db_chat.user_id),
            title=db_chat.title,
            created_at=db_chat.created_at,
            updated_at=db_chat.updated_at,
            messages=[
                MessageEntity(
                    id=msg.id,
                    user_id=str(msg.user_id),
                    content=msg.content,
                    is_ai=msg.is_ai,
                    timestamp=msg.timestamp,
                    task_id=msg.task_id,
                )
                for msg in db_chat.messages
            ],
        )

    def add_message(self, chat_id: int, message: MessageEntity) -> MessageEntity:
        db_message = Message(
            chat_id=chat_id,
            user_id=int(message.user_id),
            content=message.content,
            is_ai=message.is_ai,
            task_id=message.task_id,
        )
        self.db.add(db_message)
        self.db.commit()
        self.db.refresh(db_message)
        return MessageEntity(
            id=db_message.id,
            user_id=str(db_message.user_id),
            content=db_message.content,
            is_ai=db_message.is_ai,
            timestamp=db_message.timestamp,
            task_id=db_message.task_id,
        )

    def get_user_chats(self, user_id: int) -> List[ChatEntity]:
        db_chats = self.db.query(Chat).filter(Chat.user_id == user_id).all()
        return [
            ChatEntity(
                id=chat.id,
                user_id=str(chat.user_id),
                title=chat.title,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
            )
            for chat in db_chats
        ]

    def get_chat_messages(self, chat_id: int) -> List[MessageEntity]:
        db_chat = self.db.query(Chat).filter(Chat.id == chat_id).first()
        if not db_chat:
            return []
        return [
            MessageEntity(
                id=msg.id,
                user_id=str(msg.user_id),
                content=msg.content,
                is_ai=msg.is_ai,
                timestamp=msg.timestamp,
                task_id=msg.task_id,
            )
            for msg in db_chat.messages
        ]

    def update_message(self, message: MessageEntity) -> MessageEntity:
        db_message = self.db.query(Message).filter(Message.id == message.id).first()
        if not db_message:
            raise ValueError(f"Message with id {message.id} not found")

        # Update the message content
        setattr(db_message, "content", message.content)
        self.db.commit()
        self.db.refresh(db_message)

        return MessageEntity(
            id=db_message.id,
            user_id=str(db_message.user_id),
            content=db_message.content,
            is_ai=db_message.is_ai,
            timestamp=db_message.timestamp,
            task_id=db_message.task_id,
        )

    def create(self, chat):
        # Mock implementation for now
        return chat

    def get_by_id(self, chat_id):
        # Mock implementation for now
        return None
