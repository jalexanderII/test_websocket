from typing import (
    List,
    TypeVar,
)

from pydantic import BaseModel

from app.config.logger import get_logger
from app.config.redis import async_redis
from app.schemas.chat import Chat, Message, MessageCreate
from app.services.ai.adapter import ChatMessage
from app.services.ai.service import AIService
from app.services.chat.repository import ChatRepository
from app.utils.async_redis_utils.lrucache import AsyncLRUCache
from app.utils.async_redis_utils.queue import AsyncQueue

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


# Mock Structred response type
class StructuredResponse(BaseModel):
    """Base class for structured AI responses"""

    answer: str
    reason: str


class ChatService:
    def __init__(self, repository: ChatRepository, ai_service: AIService | None = None):
        self.repository = repository
        self.ai_service = ai_service or AIService()
        self.chat_cache = AsyncLRUCache("chat_history", capacity=1000, connection_manager=async_redis)
        self.message_queue = AsyncQueue("chat_messages", connection_manager=async_redis)

    async def create_chat(self, user_id: int) -> Chat:
        logger.info("Creating new chat for user %s", user_id)
        chat = self.repository.create_chat(user_id)
        logger.info("Chat created in database with id: %s", chat.id)
        return chat

    async def get_chat(self, chat_id: int) -> Chat | None:
        cached_chat = await self.chat_cache.get(str(chat_id))
        if cached_chat:
            return Chat.model_validate(cached_chat)

        # If not in cache, get from DB
        chat = self.repository.get_chat(chat_id)
        if chat:
            await self.chat_cache.put(str(chat_id), chat.model_dump())
        return chat

    async def get_user_chats(self, user_id: int) -> List[Chat]:
        return self.repository.get_user_chats(user_id)

    async def get_chat_history(self, chat_id: int) -> List[ChatMessage]:
        """Get chat history in a format suitable for AI context"""
        messages = self.repository.get_chat_messages(chat_id)
        return [{"role": "assistant" if msg.is_ai else "user", "content": msg.content} for msg in messages]

    async def send_message(self, message: MessageCreate) -> Message:
        chat = await self.get_chat(message.chat_id)
        if not chat:
            raise ValueError("Chat not found")

        # Create message
        db_message = self.repository.create_message(message)
        logger.debug("Created message: %s", db_message)

        # Queue for processing if user message
        if not message.is_ai:
            await self.message_queue.push(
                {
                    "chat_id": message.chat_id,
                    "content": message.content,
                    "timestamp": db_message.timestamp.isoformat(),
                    "message_id": db_message.id,
                }
            )

        # Invalidate cache
        await self.chat_cache.remove(str(message.chat_id))

        return db_message

    async def delete_chats(self, chat_ids: List[int]) -> None:
        """Delete multiple chats by their IDs"""
        if not chat_ids:
            return

        try:
            deleted_chats, deleted_messages = self.repository.delete_chats(chat_ids)
            logger.info("Deleted %d chats and %d messages", deleted_chats, deleted_messages)

            # Batch remove from cache using Redis pipeline
            async with async_redis.pipeline() as pipe:
                for chat_id in chat_ids:
                    await self.chat_cache.remove(str(chat_id))
                await pipe.execute()

        except Exception as e:
            logger.error("Failed to delete chats: %s", str(e))
            raise

    async def delete_empty_chats(self, user_id: int) -> int:
        """Delete all empty chats for a user. Returns number of chats deleted."""
        empty_chat_ids = self.repository.get_empty_chat_ids(user_id)

        if empty_chat_ids:
            await self.delete_chats(empty_chat_ids)

        return len(empty_chat_ids)

    def _generate_title_from_message(self, message: str) -> str:
        """Generate a title from the first message by taking first letter of each word"""
        # Split message into words and take first letter of each word
        words = [word.strip() for word in message.split() if word.strip()]
        if not words:
            return "New Chat"

        # Take first letter of each word, uppercase it, and join
        title = "".join(word[0].upper() for word in words if word)
        # If title would be too long, limit it
        return title[:20] if len(title) > 20 else title

    async def update_chat_title(self, chat_id: int, message: str) -> str | None:
        """Update chat title if it doesn't already have one. Returns the new title if created, None otherwise."""
        chat = await self.get_chat(chat_id)
        if not chat:
            logger.warning("Attempted to update title for non-existent chat: %s", chat_id)
            return None

        if not chat.title:  # Only update if chat doesn't have a title
            title = self._generate_title_from_message(message)
            self.repository.update_chat_title(chat_id, title)
            # Invalidate cache since we updated the chat
            await self.chat_cache.remove(str(chat_id))
            logger.info("Updated chat %s title to: %s", chat_id, title)
            return title

        return None
