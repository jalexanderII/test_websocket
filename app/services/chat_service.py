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
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.adapters.ai_adapter import OpenAIAdapter
from app.config.redis_config import redis_manager
from app.db.models import ChatDB, MessageDB, UserDB
from app.schemas.chat import Chat, Message, MessageCreate

T = TypeVar("T", bound=BaseModel)


logger = logging.getLogger(__name__)


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


# Mock Structred response type
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

    async def create_chat(self, user_id: int) -> Chat:
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

    async def get_chat(self, chat_id: int) -> Optional[Chat]:
        cached_chat = self.chat_cache.get(str(chat_id))
        if cached_chat:
            return Chat.model_validate(cached_chat)

        # If not in cache, get from DB
        db_chat = self.db.query(ChatDB).filter(ChatDB.id == chat_id).first()
        if not db_chat:
            return None

        chat = Chat.model_validate(db_chat)
        self.chat_cache.put(str(chat_id), chat.model_dump())
        return chat

    async def get_user_chats(self, user_id: int) -> List[Chat]:
        db_chats = self.db.query(ChatDB).filter(ChatDB.user_id == user_id).all()
        return [Chat.model_validate(chat) for chat in db_chats]

    async def _get_chat_history(self, chat_id: int) -> Sequence[ChatMessage]:
        messages = self.db.query(MessageDB).filter(MessageDB.chat_id == chat_id).all()
        return [{"role": "assistant" if msg.is_ai else "user", "content": msg.content} for msg in messages]

    async def send_message(self, message: MessageCreate) -> Message:
        chat = await self.get_chat(message.chat_id)
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
        logger.info("Starting AI response stream for chat %s", chat_id)

        chat = await self.get_chat(chat_id)
        if not chat:
            logger.error("Chat %s not found", chat_id)
            raise ValueError("Chat not found")

        # Get history
        history = await self._get_chat_history(chat_id)
        logger.debug("Got chat history with %d messages", len(history))

        # Create empty AI message in DB, this will be updated when the response is streamed
        db_message = MessageDB(
            chat_id=chat_id,
            content="",
            is_ai=True,
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(db_message)
        self.db.commit()
        self.db.refresh(db_message)
        logger.info("Created initial AI message with ID %s", db_message.id)

        complete_response = ""
        try:
            logger.info("Starting to stream AI response")
            async for token in self.adapter.stream_response(user_message, history=history):
                logger.debug("Received token: %s", token)
                if not isinstance(token, str):
                    logger.error("Received non-string token: %s, value: %s", type(token), token)
                    continue
                complete_response += token
                yield token

            logger.info("Stream completed, updating message in DB")
            # Update message with complete response
            self.db.execute(update(MessageDB).where(MessageDB.id == db_message.id).values(content=complete_response))
            self.db.commit()
            logger.info("Updated message %s with complete response (length: %d)", db_message.id, len(complete_response))

            self.chat_cache.remove(str(chat_id))

        except Exception:
            logger.exception("Error during streaming")
            if complete_response:
                logger.info("Saving partial response before re-raising")
                try:
                    self.db.execute(
                        update(MessageDB).where(MessageDB.id == db_message.id).values(content=complete_response)
                    )
                    self.db.commit()
                except Exception:
                    logger.exception("Failed to save partial response")
            raise

    async def stream_structured_ai_response(
        self,
        chat_id: int,
        user_message: str,
    ) -> AsyncGenerator[BaseModel, None]:
        chat = await self.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        history = await self._get_chat_history(chat_id)

        db_message = MessageDB(
            chat_id=chat_id,
            content="",
            is_ai=True,
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(db_message)
        self.db.commit()
        self.db.refresh(db_message)

        try:
            async for response in self.adapter.stream_structured_response(
                user_message,
                StructuredResponse,
                history=history,
            ):
                yield response
                # Update message with latest response
                db_message.content = response.model_dump_json()
                self.db.merge(db_message)
                self.db.commit()

        except Exception:
            # Don't need to handle partial responses as we update continuously
            raise

    def delete_chats(self, chat_ids: List[int]) -> None:
        """Delete multiple chats by their IDs"""
        if not chat_ids:
            return

        try:
            # Delete messages and chats in a transaction
            with self.db.begin():
                # Delete messages first due to foreign key constraint
                deleted_messages = (
                    self.db.query(MessageDB).filter(MessageDB.chat_id.in_(chat_ids)).delete(synchronize_session=False)
                )

                deleted_chats = self.db.query(ChatDB).filter(ChatDB.id.in_(chat_ids)).delete(synchronize_session=False)

                logger.info("Deleted %d chats and %d messages", deleted_chats, deleted_messages)

            # Batch remove from cache using Redis pipeline
            with redis_manager.pipeline() as pipe:
                for chat_id in chat_ids:
                    self.chat_cache.remove(str(chat_id))
                pipe.execute()

        except Exception as e:
            logger.error("Failed to delete chats: %s", str(e))
            self.db.rollback()
            raise

    def delete_empty_chats(self, user_id: int) -> int:
        """Delete all empty chats for a user. Returns number of chats deleted."""

        # First find all empty chats using a subquery
        empty_chat_ids = (
            self.db.query(ChatDB.id)
            .outerjoin(MessageDB, ChatDB.id == MessageDB.chat_id)
            .filter(ChatDB.user_id == user_id)
            .group_by(ChatDB.id)
            .having(func.count(MessageDB.id) == 0)
            .all()
        )

        # Extract the IDs
        empty_chat_ids = [chat_id for (chat_id,) in empty_chat_ids]

        if empty_chat_ids:
            self.db.query(ChatDB).filter(ChatDB.id.in_(empty_chat_ids)).delete(synchronize_session=False)
            self.db.commit()

            # Clear cache for deleted chats
            for chat_id in empty_chat_ids:
                self.chat_cache.remove(str(chat_id))

        return len(empty_chat_ids)
