import uuid
from typing import AsyncGenerator, List, Sequence

from pydantic import BaseModel

from app.config.logger import get_logger
from app.services.ai.adapter import ChatMessage, OpenAIAdapter
from app.services.ai.pipelines.base import AIResponse, BasePipeline
from app.services.ai.service import AIService
from app.utils.universal_serializer import safe_json_dumps

logger = get_logger(__name__)


class PlanDetails(BaseModel):
    """Details of a plan generated by the AI"""

    steps: List[str]
    reasoning: str


class PlanningPipeline(BasePipeline):
    """Pipeline that first plans steps then executes them"""

    def get_default_ai_service(self) -> AIService:
        """Override to use a more capable model for planning"""
        planning_adapter = OpenAIAdapter(model="gpt-4o-mini")  # Use a more capable model for planning
        return AIService(adapter=planning_adapter)

    def execute(
        self,
        message: str,
        history: Sequence[ChatMessage] | None = None,
    ) -> AsyncGenerator[AIResponse, None]:
        """Execute the pipeline on a message"""

        async def generate():
            # Convert sequence to list for AI service
            history_list = list(history) if history is not None else None

            # First, generate a plan
            yield AIResponse(content="Generating plan...", response_type="stream")

            # Create a unique ID for this structured response
            structured_id = str(uuid.uuid4())
            logger.info("Starting structured response generation with ID: %s", structured_id)

            last_plan = None  # Store the last plan we receive
            async for plan in self.ai_service.stream_structured_response(
                f"Plan steps to answer: {message}",
                PlanDetails,
                history=history_list,
            ):
                logger.info("Received plan: %s", plan)
                last_plan = plan
                response = AIResponse(
                    content=safe_json_dumps(plan),
                    response_type="structured",
                    metadata={"structured_id": structured_id},
                )
                yield response

            # Then execute each step using the last plan
            if last_plan:
                plan = PlanDetails.model_validate(last_plan)
                logger.info("Executing steps from plan: %s", plan)
                for i, step in enumerate(plan.steps, 1):
                    logger.info("Executing step %d: %s", i, step)
                    yield AIResponse(content=f"\nExecuting step {i}: {step}\n", response_type="stream")
                    async for token in self.ai_service.stream_chat_response(
                        f"Execute step {i}: {step}\nContext: {message}",
                        history=history_list,
                    ):
                        yield AIResponse(content=token, response_type="stream")
            else:
                logger.error("No plan was generated, cannot execute steps")
                yield AIResponse(content="Error: No plan was generated", response_type="stream")

        return generate()
