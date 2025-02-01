from typing import AsyncGenerator, Optional, Sequence

from app.adapters.ai_adapter import ChatMessage, OpenAIAdapter
from app.pipelines.base import AIResponse, BasePipeline


class StandardPipeline(BasePipeline):
    """Pipeline for standard chat interactions with streaming responses"""

    def __init__(self):
        super().__init__(name="standard")
        self.ai_adapter = OpenAIAdapter()
        self.history: list[ChatMessage] = []

    def execute(
        self, message: str, history: Optional[Sequence[ChatMessage]] = None
    ) -> AsyncGenerator[AIResponse, None]:
        """Execute standard chat pipeline with streaming response"""
        if history:
            self.history = list(history)

        async def generate():
            async for token in self.ai_adapter.stream_response(message, history=self.history):
                yield AIResponse(content=token, response_type="stream")

            # Update history with user message and final response
            self.history.extend(
                [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": token},  # Last token from stream
                ]
            )

        return generate()
