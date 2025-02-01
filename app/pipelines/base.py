from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Optional, Sequence

from pydantic import BaseModel

from app.adapters.ai_adapter import ChatMessage
from app.services.ai_service import AIService


class AIResponse(BaseModel):
    """Base class for all AI responses"""

    content: str
    response_type: str = "stream"  # stream, structured, complete
    model_output: Optional[BaseModel] = None
    metadata: Optional[Dict] = None


class BasePipeline(ABC):
    """Base class for all AI pipelines"""

    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service

    @abstractmethod
    def execute(
        self,
        message: str,
        history: Optional[Sequence[ChatMessage]] = None,
    ) -> AsyncGenerator[AIResponse, None]:
        """Execute the pipeline on a message"""

        async def generate():
            yield AIResponse(content="Not implemented", response_type="stream")

        return generate()

    async def _stream_response(self, response: AsyncGenerator[str, None]) -> AsyncGenerator[AIResponse, None]:
        """Helper to convert token stream to AIResponse stream"""
        async for token in response:
            yield AIResponse(content=token, response_type="stream")

    async def _structured_response(self, response: BaseModel) -> AsyncGenerator[AIResponse, None]:
        """Helper to convert structured response to AIResponse"""
        yield AIResponse(content=response.model_dump_json(), response_type="structured", model_output=response)
