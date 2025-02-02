from typing import AsyncGenerator, List, Type, TypeVar

from pydantic import BaseModel

from app.config.logger import get_logger
from app.services.ai.adapter import ChatMessage, OpenAIAdapter

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class AIService:
    """Service for handling AI-related operations"""

    def __init__(self, adapter: OpenAIAdapter | None = None):
        self.adapter = adapter or OpenAIAdapter()

    async def stream_chat_response(
        self,
        message: str,
        history: List[ChatMessage] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response token by token"""
        logger.info("Starting chat response stream")
        try:
            async for token in self.adapter.stream_response(message, history=history):
                if not isinstance(token, str):
                    logger.error("Received non-string token: %s", type(token))
                    continue
                yield token
        except Exception:
            logger.exception("Error streaming chat response")
            raise

    async def stream_structured_response(
        self,
        message: str,
        response_model: Type[T],
        history: List[ChatMessage] | None = None,
    ) -> AsyncGenerator[T, None]:
        """Stream a structured response using a Pydantic model"""
        logger.info("Starting structured response stream with model %s", response_model.__name__)
        try:
            async for response in self.adapter.stream_structured_response(
                message,
                response_model,
                history=history,
            ):
                yield response
        except Exception:
            logger.exception("Error streaming structured response")
            raise

    async def get_completion(self, message: str, history: List[ChatMessage] | None = None) -> str:
        return await self.adapter.generate_response(message, history)
