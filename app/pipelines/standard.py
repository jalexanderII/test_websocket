from typing import AsyncGenerator, Optional, Sequence

from app.adapters.ai_adapter import ChatMessage
from app.pipelines.base import AIResponse, BasePipeline
from app.services.ai_service import AIService


class StandardPipeline(BasePipeline):
    """Standard pipeline that streams responses directly"""

    def __init__(self, ai_service: AIService):
        super().__init__(ai_service)

    def execute(
        self,
        message: str,
        history: Optional[Sequence[ChatMessage]] = None,
    ) -> AsyncGenerator[AIResponse, None]:
        """Execute the pipeline on a message"""

        async def generate():
            # Convert sequence to list for AI service
            history_list = list(history) if history is not None else None
            async for token in self.ai_service.stream_chat_response(message, history=history_list):
                yield AIResponse(content=token, response_type="stream")

        return generate()
