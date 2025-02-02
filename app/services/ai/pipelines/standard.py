from typing import AsyncGenerator, Sequence

from app.config.settings import settings
from app.services.ai.adapter import ChatMessage, OpenAIAdapter
from app.services.ai.pipelines.base import AIResponse, BasePipeline
from app.services.ai.service import AIService


class StandardPipeline(BasePipeline):
    """Standard pipeline that streams responses directly"""

    def get_default_ai_service(self) -> AIService:
        """Use the default model configuration for standard responses"""
        standard_adapter = OpenAIAdapter(model=settings.MODEL_NAME)  # Use default model from settings
        return AIService(adapter=standard_adapter)

    def execute(
        self,
        message: str,
        history: Sequence[ChatMessage] | None = None,
    ) -> AsyncGenerator[AIResponse, None]:
        """Execute the pipeline on a message"""

        async def generate():
            # Convert sequence to list for AI service
            history_list = list(history) if history is not None else None
            async for token in self.ai_service.stream_chat_response(message, history=history_list):
                yield AIResponse(content=token, response_type="stream")

        return generate()
