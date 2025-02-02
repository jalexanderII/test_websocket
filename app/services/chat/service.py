import uuid
from typing import (
    AsyncGenerator,
    List,
    TypeVar,
)

from pydantic import BaseModel

from app.config.logger import get_logger
from app.config.redis import async_redis
from app.schemas.chat import Chat, Message, MessageCreate
from app.services.ai.adapter import ChatMessage
from app.services.ai.pipelines.base import AIResponse
from app.services.ai.service import AIService
from app.services.chat.repository import ChatRepository
from app.utils.async_redis_utils.lrucache import AsyncLRUCache
from app.utils.async_redis_utils.queue import AsyncQueue
from app.utils.universal_serializer import safe_json_dumps

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

    async def stream_ai_response(
        self,
        chat_id: int,
        user_message: str,
        task_id: str,
    ) -> AsyncGenerator[str, None]:
        logger.info("Starting AI response stream for chat %s", chat_id)

        chat = await self.get_chat(chat_id)
        if not chat:
            logger.error("Chat %s not found", chat_id)
            raise ValueError("Chat not found")

        # Get history
        history = await self.get_chat_history(chat_id)
        logger.debug("Got chat history with %d messages", len(history))

        # Create empty AI message in DB
        message = MessageCreate(chat_id=chat_id, content="", is_ai=True)
        db_message = self.repository.create_message(message, task_id=task_id)
        logger.info("Created initial AI message with ID %s and task_id %s", db_message.id, task_id)

        complete_response = ""
        try:
            logger.info("Starting to stream AI response")
            async for token in self.ai_service.stream_chat_response(user_message, history=history):
                logger.debug("Received token: %s", token)
                complete_response += token
                yield token

            logger.info("Stream completed, updating message in DB")
            # Update message with complete response
            self.repository.update_message_content(db_message.id, complete_response)
            logger.info("Updated message %s with complete response (length: %d)", db_message.id, len(complete_response))

            await self.chat_cache.remove(str(chat_id))

        except Exception:
            logger.exception("Error during streaming")
            if complete_response:
                logger.info("Saving partial response before re-raising")
                try:
                    self.repository.update_message_content(db_message.id, complete_response)
                except Exception:
                    logger.exception("Failed to save partial response")
            raise

    async def stream_structured_ai_response(
        self,
        chat_id: int,
        user_message: str,
        task_id: str,
    ) -> AsyncGenerator[BaseModel, None]:
        chat = await self.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        history = await self.get_chat_history(chat_id)

        message = MessageCreate(chat_id=chat_id, content="", is_ai=True)
        db_message = self.repository.create_message(message, task_id=task_id)
        logger.info("Created initial structured AI message with ID %s and task_id %s", db_message.id, task_id)

        structured_id = str(uuid.uuid4())

        try:
            async for stream_struc in self.ai_service.stream_structured_response(
                user_message,
                StructuredResponse,
                history=history,
            ):
                response = AIResponse(
                    content=safe_json_dumps(stream_struc),
                    response_type="structured",
                    metadata={"structured_id": structured_id},
                )
                yield response
                # Update message with latest response
                self.repository.update_message_content(db_message.id, response.model_dump_json())

        except Exception:
            # Don't need to handle partial responses as we update continuously
            raise

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
