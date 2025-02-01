from typing import AsyncGenerator, Dict, Optional, Sequence, Type

from app.adapters.ai_adapter import ChatMessage
from app.pipelines.base import AIResponse, BasePipeline
from app.pipelines.planning import PlanningPipeline
from app.pipelines.standard import StandardPipeline


class PipelineManager:
    """Manages different AI pipelines and routes messages to appropriate pipeline"""

    def __init__(self):
        # Initialize pipeline classes
        self._pipelines: Dict[str, Type[BasePipeline]] = {
            "standard": StandardPipeline,
            "planning": PlanningPipeline,
        }
        # Initialize instances dict
        self._instances: Dict[str, BasePipeline] = {}

    def get_pipeline(self, pipeline_type: str) -> BasePipeline:
        """Get or create pipeline instance"""
        if pipeline_type not in self._instances:
            if pipeline_type not in self._pipelines:
                raise ValueError(f"Unknown pipeline type: {pipeline_type}")
            # Create new instance with pipeline type as name
            pipeline_class = self._pipelines[pipeline_type]
            self._instances[pipeline_type] = pipeline_class()
        return self._instances[pipeline_type]

    async def process_message(
        self, message: str, pipeline_type: str = "standard", history: Optional[Sequence[ChatMessage]] = None
    ) -> AsyncGenerator[AIResponse, None]:
        """Process message through appropriate pipeline"""
        pipeline = self.get_pipeline(pipeline_type)
        generator = pipeline.execute(message, history=history)
        async for response in generator:
            yield response
