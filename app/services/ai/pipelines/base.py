from abc import ABC, abstractmethod
from enum import Enum
from typing import AsyncGenerator, Dict, Sequence

from pydantic import BaseModel

from app.services.ai.adapter import ChatMessage
from app.services.ai.service import AIService


class AIResponseType(str, Enum):
    STREAM = "stream"
    STRUCTURED = "structured"
    COMPLETE = "complete"


class AIResponse(BaseModel):
    """Base class for all AI responses"""

    content: str
    response_type: AIResponseType = AIResponseType.STREAM
    model_output: BaseModel | None = None
    metadata: Dict | None = None


class BasePipeline(ABC):
    """Base class for all AI pipelines"""

    def __init__(self, ai_service: AIService | None = None):
        self.ai_service = ai_service or self.get_default_ai_service()

    def get_default_ai_service(self) -> AIService:
        """Get the default AI service for this pipeline type. Override this method to customize the AI service."""
        return AIService()

    @abstractmethod
    def execute(
        self,
        message: str,
        history: Sequence[ChatMessage] | None = None,
    ) -> AsyncGenerator[AIResponse, None]:
        """Execute the pipeline on a message"""

        async def generate():
            yield AIResponse(content="Not implemented", response_type=AIResponseType.STREAM)

        return generate()

    async def _stream_response(self, response: AsyncGenerator[str, None]) -> AsyncGenerator[AIResponse, None]:
        """Helper to convert token stream to AIResponse stream"""
        async for token in response:
            yield AIResponse(content=token, response_type=AIResponseType.STREAM)

    async def _structured_response(self, response: BaseModel) -> AsyncGenerator[AIResponse, None]:
        """Helper to convert structured response to AIResponse"""
        yield AIResponse(
            content=response.model_dump_json(), response_type=AIResponseType.STRUCTURED, model_output=response
        )

    async def _complete_response(self, response: str) -> AsyncGenerator[AIResponse, None]:
        """Helper to convert complete response to AIResponse"""
        yield AIResponse(content=response, response_type=AIResponseType.COMPLETE)
