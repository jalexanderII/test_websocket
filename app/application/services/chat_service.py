import json
from typing import (
    Optional,
    AsyncGenerator,
    List,
    TypedDict,
    Literal,
    Sequence,
    Type,
    TypeVar,
)
from sqlalchemy.orm import Session
from domain.entities.chat import Chat, Message, ChatDB, MessageDB
from infrastructure.adapters.ai_adapter import OpenAIAdapter, AIAdapter
from datetime import datetime, timezone
from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.ai_adapter = AIAdapter()  # For legacy streaming
        self.structured_ai_adapter = OpenAIAdapter()  # For structured streaming

    def _is_chat_empty(self, chat_id: int) -> bool:
        """Check if a chat has any messages."""
        message_count = (
            self.db.query(MessageDB).filter(MessageDB.chat_id == chat_id).count()
        )
        return message_count == 0

    def _get_latest_empty_chat(self, user_id: int) -> Optional[Chat]:
        """Find the most recent empty chat for a user."""
        # Query chats by user, ordered by creation date (newest first)
        db_chats = (
            self.db.query(ChatDB)
            .filter(ChatDB.user_id == user_id)
            .order_by(ChatDB.created_at.desc())
            .all()
        )

        # Check each chat until we find an empty one
        for chat in db_chats:
            if self._is_chat_empty(chat.id):
                return Chat.model_validate(chat)
        return None

    def create_chat(self, user_id: int) -> Chat:
        # First try to find an existing empty chat
        existing_empty_chat = self._get_latest_empty_chat(user_id)
        if existing_empty_chat:
            return existing_empty_chat

        # If no empty chat exists, create a new one
        db_chat = ChatDB(user_id=user_id)
        self.db.add(db_chat)
        self.db.commit()
        self.db.refresh(db_chat)
        return Chat.model_validate(db_chat)

    def get_chat(self, chat_id: int) -> Optional[Chat]:
        db_chat = self.db.query(ChatDB).filter(ChatDB.id == chat_id).first()
        if not db_chat:
            return None
        return Chat.model_validate(db_chat)

    def get_user_chats(self, user_id: int) -> List[Chat]:
        db_chats = self.db.query(ChatDB).filter(ChatDB.user_id == user_id).all()
        return [Chat.model_validate(chat) for chat in db_chats]

    def _get_chat_history(self, chat_id: int) -> Sequence[ChatMessage]:
        messages = self.db.query(MessageDB).filter(MessageDB.chat_id == chat_id).all()
        history: List[ChatMessage] = []

        for msg in messages:
            # The first AI message in a chat is the system message
            if msg.is_ai and not history:
                role: Literal["user", "assistant", "system"] = "system"
            else:
                role = "assistant" if msg.is_ai else "user"
            history.append({"role": role, "content": msg.content})

        return history

    async def send_message(self, chat_id: int, user_id: int, content: str) -> Message:
        # Save user message
        user_message = MessageDB(
            chat_id=chat_id, content=content, is_ai=False, timestamp=datetime.utcnow()
        )
        self.db.add(user_message)
        self.db.commit()
        self.db.refresh(user_message)
        return Message.model_validate(user_message)

    async def stream_ai_response(
        self, chat_id: int, user_id: int, user_message: str
    ) -> AsyncGenerator[str, None]:
        # Get chat history for context
        chat = self.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        # Create AI message with empty content
        ai_message = MessageDB(
            chat_id=chat_id, content="", is_ai=True, timestamp=datetime.utcnow()
        )
        self.db.add(ai_message)
        self.db.commit()

        # Stream and accumulate response
        complete_response = ""
        try:
            async for token in self.ai_adapter.generate_stream(user_message):
                complete_response += token
                yield token

            # Update the message with complete response
            ai_message = self.db.merge(
                MessageDB(
                    id=ai_message.id,
                    chat_id=chat_id,
                    content=complete_response,
                    is_ai=True,
                    timestamp=ai_message.timestamp,
                )
            )
            self.db.commit()
        except Exception as e:
            # If there's an error, save what we have
            if complete_response:
                ai_message = self.db.merge(
                    MessageDB(
                        id=ai_message.id,
                        chat_id=chat_id,
                        content=complete_response,
                        is_ai=True,
                        timestamp=ai_message.timestamp,
                    )
                )
                self.db.commit()
            raise

    async def stream_structured_ai_response(
        self, chat_id: int, user_id: int, user_message: str, response_model: Type[T]
    ) -> AsyncGenerator[T, None]:
        # Get chat history for context
        chat = self.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        # Create AI message with empty content
        ai_message = MessageDB(
            chat_id=chat_id,
            content="",
            is_ai=True,
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(ai_message)
        self.db.commit()

        # Stream and accumulate response
        complete_response = None
        try:
            async for chunk in self.structured_ai_adapter.stream_structured_response(
                user_message, response_model
            ):
                complete_response = chunk
                yield chunk

            # Update the message with complete response
            if complete_response:
                ai_message = self.db.merge(
                    MessageDB(
                        id=ai_message.id,
                        chat_id=chat_id,
                        content=json.dumps(complete_response),
                        is_ai=True,
                        timestamp=ai_message.timestamp,
                    )
                )
                self.db.commit()
        except Exception as e:
            # If there's an error, save what we have
            if complete_response:
                ai_message = self.db.merge(
                    MessageDB(
                        id=ai_message.id,
                        chat_id=chat_id,
                        content=json.dumps(complete_response),
                        is_ai=True,
                        timestamp=ai_message.timestamp,
                    )
                )
                self.db.commit()
            raise

    async def abort_response(self, task_id: str) -> None:
        # Implement if needed
        pass

    def delete_chats(self, chat_ids: List[int]) -> None:
        """Delete multiple chats by their IDs"""
        self.db.query(MessageDB).filter(MessageDB.chat_id.in_(chat_ids)).delete(
            synchronize_session=False
        )
        self.db.query(ChatDB).filter(ChatDB.id.in_(chat_ids)).delete(
            synchronize_session=False
        )
        self.db.commit()

    def delete_empty_chats(self, user_id: int) -> int:
        """Delete all empty chats for a user. Returns number of chats deleted."""
        # Find all chats for the user
        user_chats = self.db.query(ChatDB).filter(ChatDB.user_id == user_id).all()
        deleted_count = 0

        for chat in user_chats:
            if self._is_chat_empty(chat.id):
                # Verify chat still exists before deletion
                if self.db.query(ChatDB).filter(ChatDB.id == chat.id).first():
                    self.db.delete(chat)
                    deleted_count += 1

        if deleted_count > 0:
            self.db.commit()

        return deleted_count
