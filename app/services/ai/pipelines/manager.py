from typing import AsyncGenerator, Sequence, Type

from app.services.ai.adapter import ChatMessage
from app.services.ai.pipelines.base import AIResponse, BasePipeline
from app.services.ai.pipelines.planning import PlanningPipeline
from app.services.ai.pipelines.standard import StandardPipeline


class PipelineManager:
    """Manager for different AI pipelines"""

    def __init__(self):
        self._pipelines: dict[str, Type[BasePipeline]] = {
            "standard": StandardPipeline,
            "planning": PlanningPipeline,
        }

    def get_pipeline(self, pipeline_type: str = "standard") -> BasePipeline:
        """Get a pipeline by type"""
        if pipeline_type not in self._pipelines:
            raise ValueError(f"Unknown pipeline type: {pipeline_type}")
        pipeline_class = self._pipelines[pipeline_type]
        return pipeline_class()

    async def process_message(
        self,
        message: str,
        history: Sequence[ChatMessage] | None = None,
    ) -> AsyncGenerator[AIResponse, None]:
        """Process a message through the appropriate pipeline"""
        pipeline_type = await self._determine_pipeline_type(message)
        pipeline = self.get_pipeline(pipeline_type)
        async for response in pipeline.execute(message, history=history):
            yield response

    async def _determine_pipeline_type(self, message: str) -> str:
        """Determine the appropriate pipeline for the message"""
        # TODO: Implement LLM Router logic to determine the appropriate pipeline given a message
        return "standard"
