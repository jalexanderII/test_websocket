from datetime import datetime

from app.domain.entities.chat import Chat, Message


def test_chat_creation():
    chat = Chat(
        id=1,
        user_id="user_123",
        title="Test Chat",
        created_at=datetime.now(),
        messages=[],  # Add missing messages parameter
    )
    assert chat.id == 1
    assert chat.user_id == "user_123"
    assert chat.title == "Test Chat"


def test_add_message_to_chat():
    chat = Chat(
        id=1,
        user_id="user_123",
        title="Test Chat",
        created_at=datetime.now(),
        messages=[],
    )

    message = Message(
        content="Hello",
        timestamp=datetime.now(),
        user_id="user_123",
    )

    chat.add_message(message)
    assert len(chat.messages) == 1
    assert chat.messages[0].content == "Hello"
