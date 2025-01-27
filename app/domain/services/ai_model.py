from typing import AsyncGenerator, Protocol, runtime_checkable
from abc import abstractmethod


@runtime_checkable
class AIModel(Protocol):
    @abstractmethod
    async def stream_response(self, prompt: str) -> AsyncGenerator[str, None]:
        """Stream the AI response token by token."""
        pass

    @abstractmethod
    async def generate_response(self, prompt: str) -> str:
        """Generate a complete response."""
        pass

    @abstractmethod
    async def abort(self) -> None:
        """Abort the current generation."""
        pass


class AIModelService:
    def __init__(self, ai_adapter):
        self.ai_adapter = ai_adapter

    def generate_response(self, messages):
        return self.ai_adapter.generate_response(messages)
