import uuid
from typing import Optional, AsyncGenerator, List, TypedDict, Literal, Sequence
from sqlalchemy.orm import Session
from domain.entities.chat import Chat, Message
from infrastructure.repositories.chat_repository import ChatRepository
from infrastructure.adapters.ai_adapter import OpenAIAdapter


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatService:
    def __init__(self, db: Session):
        self.chat_repository = ChatRepository(db)
        self.ai_model = OpenAIAdapter()

    def create_chat(self, user_id: int) -> Chat:
        chat = self.chat_repository.create_chat(user_id)

        if chat.id is None:
            raise ValueError("Chat was created without an ID")

        # Add system message to set context
        system_message = Message(
            user_id=str(user_id),
            content=(
                "You are a helpful AI assistant. Maintain context of the conversation "
                "and remember previous messages. When asked about previous messages, "
                "refer to them accurately."
            ),
            is_ai=True,
            task_id=str(uuid.uuid4()),
        )
        self.chat_repository.add_message(chat.id, system_message)
        return chat

    def get_chat(self, chat_id: int) -> Optional[Chat]:
        return self.chat_repository.get_chat(chat_id)

    def get_user_chats(self, user_id: int) -> list[Chat]:
        return self.chat_repository.get_user_chats(user_id)

    def _get_chat_history(self, chat_id: int) -> Sequence[ChatMessage]:
        messages = self.chat_repository.get_chat_messages(chat_id)
        history: List[ChatMessage] = []

        for msg in messages:
            # The first AI message in a chat is the system message
            if msg.is_ai and not history:
                role: Literal["user", "assistant", "system"] = "system"
            else:
                role = "assistant" if msg.is_ai else "user"
            history.append({"role": role, "content": msg.content})

        return history

    async def send_message(self, chat_id: int, user_id: int, content: str) -> Message:
        # Create and save user message
        user_message = Message(user_id=str(user_id), content=content)
        saved_message = self.chat_repository.add_message(chat_id, user_message)

        # Generate AI response with a task ID
        task_id = str(uuid.uuid4())
        ai_message = Message(
            user_id=str(user_id),
            content="",  # Will be filled by streaming
            is_ai=True,
            task_id=task_id,
        )
        ai_message = self.chat_repository.add_message(chat_id, ai_message)
        return saved_message

    async def stream_ai_response(
        self, chat_id: int, user_id: int, prompt: str
    ) -> AsyncGenerator[str, None]:
        history = self._get_chat_history(chat_id)
        # Get the last message (which should be the AI message we created)
        messages = self.chat_repository.get_chat_messages(chat_id)
        ai_message = next((msg for msg in reversed(messages) if msg.is_ai), None)

        if not ai_message:
            return

        current_content = ""
        async for token in self.ai_model.stream_response(prompt, history):
            current_content += token
            # Update the AI message content in the database
            ai_message.content = current_content
            self.chat_repository.update_message(ai_message)
            yield token

    async def abort_response(self, task_id: str) -> None:
        await self.ai_model.abort()
