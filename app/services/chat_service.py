import logging
from datetime import datetime, timezone
from typing import (
    AsyncGenerator,
    List,
    Literal,
    Optional,
    Sequence,
    TypedDict,
    TypeVar,
)

from pydantic import BaseModel
from redis_data_structures import LRUCache, Queue
from sqlalchemy.orm import Session

from app.adapters.ai_adapter import OpenAIAdapter
from app.config.redis_config import redis_manager
from app.db.models import ChatDB, MessageDB, UserDB
from app.schemas.chat import Chat, Message, MessageCreate

T = TypeVar("T", bound=BaseModel)

# Set up logging
logger = logging.getLogger(__name__)


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


class StructuredResponse(BaseModel):
    """Base class for structured AI responses"""

    answer: str
    reason: str


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.adapter = OpenAIAdapter()
        self.chat_cache = LRUCache("chat_history", capacity=1000, connection_manager=redis_manager)
        self.message_queue = Queue("chat_messages", connection_manager=redis_manager)

    def create_chat(self, user_id: int) -> Chat:
        # First check if user exists, if not create one
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

        # Create new chat
        db_chat = ChatDB(user_id=user_id)
        logger.info("Creating new chat: %s", db_chat)

        self.db.add(db_chat)
        self.db.commit()
        self.db.refresh(db_chat)

        logger.info("Chat created in database with id: %s", db_chat.id)
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
        return [{"role": "assistant" if msg.is_ai else "user", "content": msg.content} for msg in messages]

    async def send_message(self, message: MessageCreate, user_id: int) -> Message:
        # Verify chat exists
        chat = self.get_chat(message.chat_id)
        if not chat:
            raise ValueError("Chat not found")

        # Create message
        db_message = MessageDB(
            chat_id=message.chat_id,
            content=message.content,
            is_ai=message.is_ai,
            timestamp=datetime.now(timezone.utc),
        )
        logger.debug("Creating message: %s", db_message)

        self.db.add(db_message)
        self.db.commit()
        self.db.refresh(db_message)

        # Queue for processing if user message
        if not message.is_ai:
            self.message_queue.push(
                {
                    "chat_id": message.chat_id,
                    "content": message.content,
                    "timestamp": db_message.timestamp.isoformat(),
                    "message_id": db_message.id,
                }
            )

        # Invalidate cache
        self.chat_cache.remove(str(message.chat_id))

        return Message.model_validate(db_message)

    async def stream_ai_response(
        self,
        chat_id: int,
        user_message: str,
    ) -> AsyncGenerator[str, None]:
        # Get chat
        chat = self.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        # Get history
        history = self._get_chat_history(chat_id)

        # Create AI message
        ai_message = await self.send_message(
            MessageCreate(
                chat_id=chat_id,
                content="",
                is_ai=True,
            ),
            chat.user_id,
        )

        # Stream response
        complete_response = ""
        try:
            async for token in self.adapter.stream_response(user_message, history=history):
                complete_response += token
                yield token

            # Update message with complete response
            ai_message.content = complete_response
            self.db.merge(ai_message)
            self.db.commit()

        except Exception:
            if complete_response:
                ai_message.content = complete_response
                self.db.merge(ai_message)
                self.db.commit()
            raise

    async def stream_structured_ai_response(
        self,
        chat_id: int,
        user_message: str,
    ) -> AsyncGenerator[StructuredResponse, None]:
        # Get chat
        chat = self.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        # Get history
        history = self._get_chat_history(chat_id)

        # Create AI message
        ai_message = await self.send_message(
            MessageCreate(
                chat_id=chat_id,
                content="",
                is_ai=True,
            ),
            chat.user_id,
        )

        try:
            async for response in self.adapter.stream_structured_response(
                user_message,
                StructuredResponse,
                history=history,
            ):
                yield response
                # Update message with latest response
                ai_message.content = response.model_dump_json()
                self.db.merge(ai_message)
                self.db.commit()

        except Exception:
            # Don't need to handle partial responses as we update continuously
            raise

    def delete_chats(self, chat_ids: List[int]) -> None:
        """Delete multiple chats by their IDs"""
        self.db.query(MessageDB).filter(MessageDB.chat_id.in_(chat_ids)).delete(synchronize_session=False)
        self.db.query(ChatDB).filter(ChatDB.id.in_(chat_ids)).delete(synchronize_session=False)
        self.db.commit()

        # Clear cache for deleted chats
        for chat_id in chat_ids:
            self.chat_cache.remove(str(chat_id))

    def delete_empty_chats(self, user_id: int) -> int:
        """Delete all empty chats for a user. Returns number of chats deleted."""
        empty_chats = []
        user_chats = self.db.query(ChatDB).filter(ChatDB.user_id == user_id).all()

        for chat in user_chats:
            message_count = self.db.query(MessageDB).filter(MessageDB.chat_id == chat.id).count()
            if message_count == 0:
                empty_chats.append(chat.id)
                self.db.delete(chat)

        if empty_chats:
            self.db.commit()
            # Clear cache for deleted chats
            for chat_id in empty_chats:
                self.chat_cache.remove(str(chat_id))

        return len(empty_chats)
