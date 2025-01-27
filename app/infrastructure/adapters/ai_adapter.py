from typing import (
    AsyncGenerator,
    Optional,
    List,
    Sequence,
    TypedDict,
    Literal,
    cast,
)
from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletionMessageParam
from config import OPENAI_API_KEY, MODEL_NAME
from domain.services.ai_model import AIModel


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


class OpenAIAdapter(AIModel):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.model = MODEL_NAME
        self.current_stream: Optional[AsyncStream] = None

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
            self.current_stream = stream
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            print(f"Error in stream_response: {e}")
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

    async def abort(self) -> None:
        if self.current_stream:
            await self.current_stream.close()
            self.current_stream = None


class AIAdapter:
    def __init__(self):
        pass

    def generate_response(self, messages):
        # Mock implementation for now
        return "Test response"
