from typing import AsyncGenerator, List, Optional, Sequence

import pytest

from app.adapters.ai_adapter import ChatMessage
from app.pipelines.base import AIResponse, BasePipeline
from app.pipelines.manager import PipelineManager
from app.pipelines.planning import PlanDetails, PlanningPipeline
from app.pipelines.standard import StandardPipeline


class MockPipeline(BasePipeline):
    """Mock pipeline for testing"""

    def __init__(self):
        super().__init__(name="mock")
        self.messages: List[str] = []
        self.history: List[ChatMessage] = []

    async def execute(
        self, message: str, history: Optional[Sequence[ChatMessage]] = None
    ) -> AsyncGenerator[AIResponse, None]:
        self.messages.append(message)
        if history:
            self.history = list(history)
        yield AIResponse(content="mock response", response_type="stream")


class MockAIAdapter:
    """Mock AI adapter for testing pipelines"""

    async def stream_response(
        self, prompt: str, history: Optional[Sequence[ChatMessage]] = None
    ) -> AsyncGenerator[str, None]:
        yield "test response"

    async def stream_structured_response(
        self, prompt: str, response_model: type, history: Optional[Sequence[ChatMessage]] = None
    ) -> AsyncGenerator[PlanDetails, None]:
        yield PlanDetails(steps=["step 1", "step 2"], reasoning="test reasoning")


@pytest.fixture
def test_history() -> List[ChatMessage]:
    return [{"role": "user", "content": "previous message"}]


@pytest.fixture
def pipeline_manager():
    manager = PipelineManager()
    # Add mock pipeline for testing
    manager._pipelines["mock"] = MockPipeline
    return manager


@pytest.fixture
def mock_ai_adapter(monkeypatch):
    adapter = MockAIAdapter()
    monkeypatch.setattr("app.pipelines.standard.OpenAIAdapter", lambda: adapter)
    monkeypatch.setattr("app.pipelines.planning.OpenAIAdapter", lambda: adapter)
    return adapter


@pytest.mark.asyncio
async def test_get_pipeline(pipeline_manager):
    # Test getting standard pipeline
    standard = pipeline_manager.get_pipeline("standard")
    assert standard.name == "standard"

    # Test getting same instance
    standard2 = pipeline_manager.get_pipeline("standard")
    assert standard is standard2

    # Test getting mock pipeline
    mock = pipeline_manager.get_pipeline("mock")
    assert mock.name == "mock"

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

    # Verify message was passed to pipeline
    mock_pipeline = pipeline_manager.get_pipeline("mock")
    assert mock_pipeline.messages == ["test message"]
    assert mock_pipeline.history == test_history


@pytest.mark.asyncio
async def test_standard_pipeline(mock_ai_adapter, test_history):
    pipeline = StandardPipeline()

    responses = []
    async for response in pipeline.execute("test message", history=test_history):
        responses.append(response)

    assert len(responses) == 1
    assert responses[0].content == "test response"
    assert responses[0].response_type == "stream"

    # Verify history was updated
    assert len(pipeline.history) == 3  # original + user message + AI response
    assert pipeline.history[-2]["role"] == "user"
    assert pipeline.history[-2]["content"] == "test message"
    assert pipeline.history[-1]["role"] == "assistant"
    assert pipeline.history[-1]["content"] == "test response"


@pytest.mark.asyncio
async def test_planning_pipeline(mock_ai_adapter, test_history):
    pipeline = PlanningPipeline()

    responses = []
    async for response in pipeline.execute("test message", history=test_history):
        responses.append(response)

    # Should have multiple responses:
    # 1. Plan outline (stream)
    # 2. Plan details (structured)
    # 3. Step executions (stream per step)
    # 4. Summary (stream)
    assert len(responses) > 3

    # Verify we got different types of responses
    response_types = [r.response_type for r in responses]
    assert "stream" in response_types
    assert "structured" in response_types

    # Verify history was maintained
    assert len(pipeline.history) > 3  # Should have multiple interactions
    assert all(msg["role"] in ["user", "assistant"] for msg in pipeline.history)
