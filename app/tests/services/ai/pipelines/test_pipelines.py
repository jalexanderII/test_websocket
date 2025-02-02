from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai.adapter import ChatMessage
from app.services.ai.pipelines.planning import PlanDetails, PlanningPipeline
from app.services.ai.pipelines.standard import StandardPipeline
from app.services.ai.service import AIService


class AsyncIterator:
    """Helper class to make async iterators from lists"""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            item = self.items[self.index]
            self.index += 1
            return item
        except IndexError:
            raise StopAsyncIteration


@pytest.fixture
def mock_ai_service():
    """Create a mock AI service that returns predictable responses"""
    service = AsyncMock(spec=AIService)

    # Create mock responses
    stream_responses = ["test token 1", "test token 2"]
    structured_responses = [PlanDetails(steps=["step 1", "step 2"], reasoning="test reasoning")]

    # Create async iterators
    stream_iterator = AsyncIterator(stream_responses)
    structured_iterator = AsyncIterator(structured_responses)

    # Set up the mock methods to return the iterators
    service.stream_chat_response = MagicMock(return_value=stream_iterator)
    service.stream_structured_response = MagicMock(return_value=structured_iterator)

    return service


@pytest.fixture
def test_history() -> List[ChatMessage]:
    return [{"role": "user", "content": "previous message"}]


@pytest.mark.asyncio
async def test_standard_pipeline_execution(mock_ai_service):
    """Test that StandardPipeline correctly streams responses"""
    pipeline = StandardPipeline()
    pipeline.ai_service = mock_ai_service  # Override the default service

    responses = []
    async for response in pipeline.execute("test message", history=[]):
        responses.append(response)

    assert len(responses) == 2
    assert all(r.response_type == "stream" for r in responses)
    assert [r.content for r in responses] == ["test token 1", "test token 2"]

    # Verify AI service was called correctly
    mock_ai_service.stream_chat_response.assert_called_once_with("test message", history=[])


@pytest.mark.asyncio
async def test_planning_pipeline_execution(mock_ai_service):
    """Test that PlanningPipeline correctly handles the planning and execution flow"""
    pipeline = PlanningPipeline()
    pipeline.ai_service = mock_ai_service  # Override the default service

    responses = []
    async for response in pipeline.execute("test message", history=[]):
        responses.append(response)

    # Verify we get the expected sequence of responses:
    # 1. Initial "Generating plan..." message
    # 2. Plan details (structured)
    # 3. Step execution messages and responses
    assert len(responses) > 4  # Initial + plan + 2 steps with responses

    # Check the sequence of responses
    assert responses[0].content == "Generating plan..."
    assert responses[0].response_type == "stream"

    # Verify we got a structured plan response
    plan_responses = [r for r in responses if r.response_type == "structured"]
    assert len(plan_responses) == 1
    assert "structured_id" in plan_responses[0].metadata

    # Verify we got step execution responses
    step_responses = [r for r in responses if "Executing step" in r.content]
    assert len(step_responses) == 2  # One for each step

    # Verify AI service calls
    assert mock_ai_service.stream_structured_response.call_count == 1
    assert mock_ai_service.stream_chat_response.call_count == 2  # Once per step
