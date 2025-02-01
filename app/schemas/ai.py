from abc import abstractmethod
from typing import (
    AsyncGenerator,
    Literal,
    Protocol,
    Sequence,
    Type,
    TypedDict,
    TypeVar,
    runtime_checkable,
)

from pydantic import BaseModel


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class AIModel(Protocol):
    @abstractmethod
    async def stream_response(
        self, prompt: str, history: Sequence[ChatMessage] | None = None
    ) -> AsyncGenerator[str, None]:
        """Stream the AI response token by token."""
        pass

    @abstractmethod
    async def stream_structured_response(
        self,
        prompt: str,
        response_model: Type[T],
        history: Sequence[ChatMessage] | None = None,
    ) -> AsyncGenerator[T, None]:
        """Stream the AI response as structured data."""
        pass

    @abstractmethod
    async def generate_response(self, prompt: str, history: Sequence[ChatMessage] | None = None) -> str:
        """Generate a complete response."""
        pass
