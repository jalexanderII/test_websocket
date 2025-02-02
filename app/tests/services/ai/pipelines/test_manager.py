from typing import AsyncGenerator, List, Sequence
from unittest.mock import AsyncMock

import pytest

from app.services.ai.adapter import ChatMessage, OpenAIAdapter
from app.services.ai.pipelines.base import AIResponse, BasePipeline
from app.services.ai.pipelines.manager import PipelineManager
from app.services.ai.pipelines.planning import PlanDetails, PlanningPipeline
from app.services.ai.pipelines.standard import StandardPipeline
from app.services.ai.service import AIService


@pytest.fixture
def mock_ai_service():
    """Create a mock AI service that returns predictable responses"""
    service = AsyncMock(spec=AIService)

    async def mock_stream(*args, **kwargs):
        yield "test response"

    async def mock_structured(*args, **kwargs):
        yield PlanDetails(steps=["step 1", "step 2"], reasoning="test reasoning")

    service.stream_chat_response = AsyncMock(side_effect=mock_stream)
    service.stream_structured_response = AsyncMock(side_effect=mock_structured)
    return service


@pytest.fixture
def mock_pipeline(mock_ai_service):
    """Create a mock pipeline that uses the mock AI service"""

    class TestPipeline(BasePipeline):
        def get_default_ai_service(self) -> AIService:
            return mock_ai_service

        def execute(
            self, message: str, history: Sequence[ChatMessage] | None = None
        ) -> AsyncGenerator[AIResponse, None]:
            async def generate():
                yield AIResponse(content="mock response", response_type="stream")

            return generate()

    return TestPipeline


@pytest.fixture
def pipeline_manager(mock_pipeline):
    manager = PipelineManager()
    # Add mock pipeline for testing
    manager._pipelines["mock"] = mock_pipeline
    return manager


@pytest.fixture
def test_history() -> List[ChatMessage]:
    return [{"role": "user", "content": "previous message"}]


@pytest.mark.asyncio
async def test_get_pipeline_creates_new_instance(pipeline_manager):
    """Test that get_pipeline creates a new instance each time"""
    pipeline1 = pipeline_manager.get_pipeline("mock")
    pipeline2 = pipeline_manager.get_pipeline("mock")

    assert isinstance(pipeline1, BasePipeline)
    assert isinstance(pipeline2, BasePipeline)
    assert pipeline1 is not pipeline2  # Should be different instances


@pytest.mark.asyncio
async def test_get_pipeline_with_invalid_type(pipeline_manager):
    """Test that getting an invalid pipeline type raises ValueError"""
    with pytest.raises(ValueError, match="Unknown pipeline type"):
        pipeline_manager.get_pipeline("invalid")


@pytest.mark.asyncio
async def test_process_message_uses_determined_pipeline(pipeline_manager, test_history):
    """Test that process_message uses the pipeline determined by _determine_pipeline_type"""
    # Mock _determine_pipeline_type to always return "mock"
    pipeline_manager._determine_pipeline_type = AsyncMock(return_value="mock")

    responses = []
    async for response in pipeline_manager.process_message("test message", history=test_history):
        responses.append(response)

    assert len(responses) == 1
    assert responses[0].content == "mock response"
    assert responses[0].response_type == "stream"

    # Verify _determine_pipeline_type was called with the message
    pipeline_manager._determine_pipeline_type.assert_called_once_with("test message")


@pytest.mark.asyncio
async def test_standard_pipeline_uses_default_service():
    """Test that StandardPipeline uses the default AI service configuration"""
    pipeline = StandardPipeline()
    assert isinstance(pipeline.ai_service, AIService)
    assert isinstance(pipeline.ai_service.adapter, OpenAIAdapter)


@pytest.mark.asyncio
async def test_planning_pipeline_uses_custom_service():
    """Test that PlanningPipeline uses a custom AI service configuration"""
    pipeline = PlanningPipeline()
    assert isinstance(pipeline.ai_service, AIService)
    assert isinstance(pipeline.ai_service.adapter, OpenAIAdapter)
    assert pipeline.ai_service.adapter.model == "gpt-4o-mini"  # Verify custom model is used
