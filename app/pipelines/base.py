from typing import AsyncGenerator, Optional, Sequence

from pydantic import BaseModel

from app.adapters.ai_adapter import ChatMessage


class AIResponse(BaseModel):
    """Base class for all AI responses"""

    content: str
    response_type: str = "stream"  # stream, structured, complete
    model_output: Optional[BaseModel] = None


class BasePipeline:
    """Base class for all AI pipelines"""

    def __init__(self, name: Optional[str] = None):
        self.name = name or self.__class__.__name__

    def execute(
        self, message: str, history: Optional[Sequence[ChatMessage]] = None
    ) -> AsyncGenerator[AIResponse, None]:
        """Execute the pipeline on the input message"""
        raise NotImplementedError("Pipeline must implement execute method")

    async def _stream_response(self, response: AsyncGenerator[str, None]) -> AsyncGenerator[AIResponse, None]:
        """Helper to convert token stream to AIResponse stream"""
        async for token in response:
            yield AIResponse(content=token, response_type="stream")

    async def _structured_response(self, response: BaseModel) -> AsyncGenerator[AIResponse, None]:
        """Helper to convert structured response to AIResponse"""
        yield AIResponse(content=response.model_dump_json(), response_type="structured", model_output=response)
