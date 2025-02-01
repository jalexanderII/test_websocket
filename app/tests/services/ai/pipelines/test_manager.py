from typing import AsyncGenerator, List, Sequence

import pytest

from app.services.ai.adapter import ChatMessage, OpenAIAdapter
from app.services.ai.pipelines.base import AIResponse, BasePipeline
from app.services.ai.pipelines.manager import PipelineManager
from app.services.ai.pipelines.planning import PlanDetails, PlanningPipeline
from app.services.ai.pipelines.standard import StandardPipeline
from app.services.ai.service import AIService


class MockPipeline(BasePipeline):
    """Mock pipeline for testing"""

    def __init__(self, ai_service: AIService):
        super().__init__(ai_service)
        self.messages: List[str] = []
        self.history: List[ChatMessage] = []

    def execute(
        self, message: str, history: Sequence[ChatMessage] | None = None
    ) -> AsyncGenerator[AIResponse, None]:
        async def generate():
            self.messages.append(message)
            if history:
                self.history = list(history)
            yield AIResponse(content="mock response", response_type="stream")

        return generate()


class MockAIAdapter(OpenAIAdapter):
    """Mock AI adapter for testing pipelines"""

    async def stream_response(
        self, prompt: str, history: Sequence[ChatMessage] | None = None
    ) -> AsyncGenerator[str, None]:
        yield "test response"

    async def stream_structured_response(
        self, prompt: str, response_model: type, history: Sequence[ChatMessage] | None = None
    ) -> AsyncGenerator[PlanDetails, None]:
        yield PlanDetails(steps=["step 1", "step 2"], reasoning="test reasoning")


@pytest.fixture
def test_history() -> List[ChatMessage]:
    return [{"role": "user", "content": "previous message"}]


@pytest.fixture
def mock_ai_service():
    return AIService(adapter=MockAIAdapter())


@pytest.fixture
def pipeline_manager(mock_ai_service):
    manager = PipelineManager(ai_service=mock_ai_service)
    # Add mock pipeline for testing
    manager._pipelines["mock"] = MockPipeline
    return manager


@pytest.mark.asyncio
async def test_get_pipeline(pipeline_manager):
    # Test getting standard pipeline
    standard = pipeline_manager.get_pipeline("standard")
    assert isinstance(standard, StandardPipeline)

    # Test getting mock pipeline
    mock = pipeline_manager.get_pipeline("mock")
    assert isinstance(mock, MockPipeline)

    # Test invalid pipeline type
    with pytest.raises(ValueError):
        pipeline_manager.get_pipeline("invalid")


@pytest.mark.asyncio
async def test_process_message(pipeline_manager, test_history):
    # Test processing with mock pipeline
    responses = []
    async for response in pipeline_manager.process_message("test message", "mock", history=test_history):
        responses.append(response)

    assert len(responses) == 1
    assert responses[0].content == "mock response"
    assert responses[0].response_type == "stream"

    # Get a new instance to verify message was passed
    mock_pipeline = pipeline_manager.get_pipeline("mock")
    mock_pipeline.messages = []  # Reset messages
    async for _ in mock_pipeline.execute("test message", history=test_history):
        pass
    assert mock_pipeline.messages == ["test message"]
    assert mock_pipeline.history == test_history


@pytest.mark.asyncio
async def test_standard_pipeline(mock_ai_service):
    pipeline = StandardPipeline(mock_ai_service)

    responses = []
    async for response in pipeline.execute("test message", history=[]):
        responses.append(response)

    assert len(responses) == 1
    assert responses[0].content == "test response"
    assert responses[0].response_type == "stream"


@pytest.mark.asyncio
async def test_planning_pipeline(mock_ai_service):
    pipeline = PlanningPipeline(mock_ai_service)

    responses = []
    async for response in pipeline.execute("test message", history=[]):
        responses.append(response)

    # Should have multiple responses:
    # 1. Initial "Generating plan..." message
    # 2. Plan details (structured)
    # 3. Step executions (stream per step)
    assert len(responses) > 2

    # Verify we got different types of responses
    response_types = [r.response_type for r in responses]
    assert "stream" in response_types
    assert "structured" in response_types
