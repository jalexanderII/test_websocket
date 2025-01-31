import logging
from typing import (
    AsyncGenerator,
    List,
    Literal,
    Optional,
    Sequence,
    Type,
    TypedDict,
    TypeVar,
    cast,
)

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from app.config.env import MODEL_NAME, OPENAI_API_KEY
from app.schemas.ai_model import AIModel

T = TypeVar("T", bound=BaseModel)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


class OpenAIAdapter(AIModel):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.model = MODEL_NAME

    def _convert_to_openai_messages(self, messages: Sequence[ChatMessage]) -> List[ChatCompletionMessageParam]:
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
            logger.exception("Error in stream_response: %s", e)
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
            logger.exception("Error in stream_structured_response: %s", e)
            raise

    async def generate_response(self, prompt: str, history: Optional[Sequence[ChatMessage]] = None) -> str:
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
            logger.exception("Error in generate_response: %s", e)
            raise
