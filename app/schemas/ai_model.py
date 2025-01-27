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

