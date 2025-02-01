import logging
from typing import AsyncGenerator, List, Optional, Type, TypeVar

from pydantic import BaseModel

from app.services.ai.adapter import ChatMessage, OpenAIAdapter

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class AIService:
    """Service for handling AI-related operations"""

    def __init__(self, adapter: Optional[OpenAIAdapter] = None):
        self.adapter = adapter or OpenAIAdapter()

    async def stream_chat_response(
        self,
        message: str,
        history: Optional[List[ChatMessage]] = None,
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
        history: Optional[List[ChatMessage]] = None,
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

    async def get_completion(
        self,
        message: str,
        history: Optional[List[ChatMessage]] = None,
    ) -> str:
        """Get a single completion response"""
        logger.info("Getting completion response")
        try:
            complete_response = ""
            async for token in self.stream_chat_response(message, history):
                complete_response += token
            return complete_response
        except Exception:
            logger.exception("Error getting completion")
            raise
