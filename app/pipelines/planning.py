from typing import AsyncGenerator, List, Optional, Sequence

from pydantic import BaseModel

from app.adapters.ai_adapter import ChatMessage, OpenAIAdapter
from app.pipelines.base import AIResponse, BasePipeline


class PlanDetails(BaseModel):
    """Structured response for plan details"""

    steps: List[str]
    reasoning: str


class PlanningPipeline(BasePipeline):
    """Pipeline for planning-based interactions with multiple AI steps"""

    def __init__(self):
        super().__init__(name="planning")
        self.ai_adapter = OpenAIAdapter()
        self.history: list[ChatMessage] = []

    def execute(
        self, message: str, history: Optional[Sequence[ChatMessage]] = None
    ) -> AsyncGenerator[AIResponse, None]:
        """Execute multi-step planning pipeline"""
        if history:
            self.history = list(history)

        async def generate():
            # Step 1: Generate initial plan outline (streaming)
            outline = ""
            async for token in self.ai_adapter.stream_response(
                f"Create a brief outline for: {message}", history=self.history
            ):
                outline += token
                yield AIResponse(content=token, response_type="stream")

            self.history.extend(
                [
                    {"role": "user", "content": f"Create a brief outline for: {message}"},
                    {"role": "assistant", "content": outline},
                ]
            )

            # Step 2: Generate detailed plan (structured)
            async for response in self.ai_adapter.stream_structured_response(
                message, PlanDetails, history=self.history
            ):
                yield AIResponse(content=response.model_dump_json(), response_type="structured", model_output=response)

                # Store the plan for step 3
                plan = response

            self.history.append({"role": "assistant", "content": response.model_dump_json()})

            # Step 3: Execute plan steps
            for i, step in enumerate(plan.steps, 1):
                step_response = ""
                # Stream execution for each step
                async for token in self.ai_adapter.stream_response(f"Executing step {i}: {step}", history=self.history):
                    step_response += token
                    yield AIResponse(content=token, response_type="stream")

                self.history.extend(
                    [
                        {"role": "user", "content": f"Executing step {i}: {step}"},
                        {"role": "assistant", "content": step_response},
                    ]
                )

            # Step 4: Generate summary
            summary = ""
            async for token in self.ai_adapter.stream_response("Summarize the execution results", history=self.history):
                summary += token
                yield AIResponse(content=token, response_type="stream")

            self.history.extend(
                [
                    {"role": "user", "content": "Summarize the execution results"},
                    {"role": "assistant", "content": summary},
                ]
            )

        return generate()
