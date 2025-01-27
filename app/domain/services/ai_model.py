from typing import (
    AsyncGenerator,
    Protocol,
    runtime_checkable,
    Optional,
    Sequence,
    TypedDict,
    Literal,
    TypeVar,
    Type,
)
from abc import abstractmethod
from pydantic import BaseModel


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class AIModel(Protocol):
    @abstractmethod
    async def stream_response(
        self, prompt: str, history: Optional[Sequence[ChatMessage]] = None
    ) -> AsyncGenerator[str, None]:
        """Stream the AI response token by token."""
        pass

    @abstractmethod
    async def stream_structured_response(
        self,
        prompt: str,
        response_model: Type[T],
        history: Optional[Sequence[ChatMessage]] = None,
    ) -> AsyncGenerator[T, None]:
        """Stream the AI response as structured data."""
        pass

    @abstractmethod
    async def generate_response(
        self, prompt: str, history: Optional[Sequence[ChatMessage]] = None
    ) -> str:
        """Generate a complete response."""
        pass


class AIModelService:
    def __init__(self, model: AIModel):
        self.model = model

    async def generate_response(self, prompt: str) -> str:
        return await self.model.generate_response(prompt)

    async def stream_structured_response(
        self, prompt: str, response_model: Type[T]
    ) -> AsyncGenerator[T, None]:
        async for chunk in await self.model.stream_structured_response(
            prompt, response_model
        ):
            yield chunk
