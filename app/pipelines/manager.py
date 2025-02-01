from typing import AsyncGenerator, Optional, Sequence

from app.adapters.ai_adapter import ChatMessage
from app.pipelines.base import AIResponse, BasePipeline
from app.pipelines.planning import PlanningPipeline
from app.pipelines.standard import StandardPipeline
from app.services.ai_service import AIService


class PipelineManager:
    """Manager for different AI pipelines"""

    def __init__(self, ai_service: Optional[AIService] = None):
        self.ai_service = ai_service or AIService()
        self._pipelines = {
            "standard": StandardPipeline,
            "planning": PlanningPipeline,
        }

    def get_pipeline(self, pipeline_type: str = "standard") -> BasePipeline:
        """Get a pipeline by type"""
        if pipeline_type not in self._pipelines:
            raise ValueError(f"Unknown pipeline type: {pipeline_type}")
        return self._pipelines[pipeline_type](self.ai_service)

    async def process_message(
        self,
        message: str,
        pipeline_type: str = "standard",
        history: Optional[Sequence[ChatMessage]] = None,
    ) -> AsyncGenerator[AIResponse, None]:
        """Process a message through the appropriate pipeline"""
        pipeline = self.get_pipeline(pipeline_type)
        async for response in pipeline.execute(message, history=history):
            yield response
