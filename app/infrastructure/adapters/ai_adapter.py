from typing import (
    AsyncGenerator,
    Optional,
    List,
    Sequence,
    TypedDict,
    Literal,
    cast,
    Type,
    TypeVar,
)
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from config import OPENAI_API_KEY, MODEL_NAME
from domain.services.ai_model import AIModel
from pydantic import BaseModel
import os


T = TypeVar("T", bound=BaseModel)


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


class OpenAIAdapter(AIModel):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.model = MODEL_NAME

    def _convert_to_openai_messages(
        self, messages: Sequence[ChatMessage]
    ) -> List[ChatCompletionMessageParam]:
        return [
            cast(
                ChatCompletionMessageParam,
                {"role": msg["role"], "content": msg["content"]},
            )
            for msg in messages
        ]

    async def stream_response(
        self, prompt: str, history: Optional[Sequence[ChatMessage]] = None
    ) -> AsyncGenerator[str, None]:
        try:
            messages = self._convert_to_openai_messages(history) if history else []
            messages.append(
                cast(
                    ChatCompletionMessageParam,
                    {"role": "user", "content": prompt},
                )
            )

            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            print(f"Error in stream_response: {e}")
            raise

    async def stream_structured_response(
        self,
        prompt: str,
        response_model: Type[T],
        history: Optional[Sequence[ChatMessage]] = None,
    ) -> AsyncGenerator[T, None]:
        try:
            messages = self._convert_to_openai_messages(history) if history else []
            messages.append(
                cast(
                    ChatCompletionMessageParam,
                    {"role": "user", "content": prompt},
                )
            )

            async with self.client.beta.chat.completions.stream(
                model=self.model,
                messages=messages,
                response_format=response_model,
            ) as stream:
                async for event in stream:
                    if event.type == "content.delta" and event.parsed is not None:
                        yield cast(T, event.parsed)
        except Exception as e:
            print(f"Error in stream_structured_response: {e}")
            raise

    async def generate_response(
        self, prompt: str, history: Optional[Sequence[ChatMessage]] = None
    ) -> str:
        try:
            messages = self._convert_to_openai_messages(history) if history else []
            messages.append(
                cast(
                    ChatCompletionMessageParam,
                    {"role": "user", "content": prompt},
                )
            )

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"Error in generate_response: {e}")
            raise


class AIAdapter:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        try:
            stream = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            print(f"Error in AI generation: {e}")
            raise

    def generate_response(self, messages):
        # Mock implementation for now
        return "Test response"
