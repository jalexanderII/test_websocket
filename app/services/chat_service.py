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
    Callable,
    Coroutine,
    Any,
)
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from pydantic import BaseModel
from redis_data_structures import LRUCache, Queue, PriorityQueue
from app.adapters.ai_adapter import OpenAIAdapter
from app.config.redis_config import redis_manager
from app.db.models import ChatDB, MessageDB
from app.schemas.chat import Chat, Message


T = TypeVar("T", bound=BaseModel)


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.structured_ai_adapter = OpenAIAdapter()
        # Initialize Redis data structures with connection manager
        self.chat_cache = LRUCache(
            "chat_history", capacity=1000, connection_manager=redis_manager
        )
        self.message_queue = Queue("chat_messages", connection_manager=redis_manager)
        self.priority_messages = PriorityQueue(
            "priority_messages", connection_manager=redis_manager
        )

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
        # Try cache first
        cached_chat = self.chat_cache.get(str(chat_id))
        if cached_chat:
            return Chat.model_validate(cached_chat)

        # If not in cache, get from DB
        db_chat = self.db.query(ChatDB).filter(ChatDB.id == chat_id).first()
        if not db_chat:
            return None

        chat = Chat.model_validate(db_chat)
        # Cache the result
        self.chat_cache.put(str(chat_id), chat.model_dump())
        return chat

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

    async def send_message(
        self, chat_id: Optional[int], content: str, priority: int = 1
    ) -> Message:
        # Save user message
        user_message = MessageDB(
            chat_id=chat_id,
            content=content,
            is_ai=False,
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(user_message)
        self.db.commit()
        self.db.refresh(user_message)

        # Queue message for AI processing with priority
        self.priority_messages.push(
            {
                "chat_id": chat_id,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message_id": user_message.id,
            },
            priority,
        )

        # Invalidate chat cache since we added a new message
        if chat_id:
            self.chat_cache.remove(str(chat_id))

        return Message.model_validate(user_message)

    async def stream_ai_response(
        self,
        chat_id: int,
        user_message: str,
        interim_message_handler: Optional[
            Callable[[str], Coroutine[Any, Any, None]]
        ] = None,
    ) -> AsyncGenerator[str, None]:
        # Get chat history for context
        chat = self.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        # Get chat history
        history = self._get_chat_history(chat_id)

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
        complete_response = ""
        try:
            async for token in self.structured_ai_adapter.stream_response(
                user_message, history=history
            ):
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

            # Invalidate chat cache since we added a new message
            self.chat_cache.remove(str(chat_id))

        except Exception:
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
                # Invalidate chat cache
                self.chat_cache.remove(str(chat_id))
            raise

    async def stream_structured_ai_response(
        self,
        chat_id: int,
        user_message: str,
        response_model: Type[T],
        interim_message_handler: Optional[
            Callable[[str], Coroutine[Any, Any, None]]
        ] = None,
    ) -> AsyncGenerator[T, None]:
        # Get chat history for context
        chat = self.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        # Get chat history
        history = self._get_chat_history(chat_id)

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
                user_message, response_model, history=history
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
        except Exception:
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
