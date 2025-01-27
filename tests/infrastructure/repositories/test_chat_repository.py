from app.infrastructure.repositories.chat_repository import ChatRepository
from app.domain.entities.chat import Chat
from datetime import datetime


def test_create_chat(test_db):
    # Arrange
    repo = ChatRepository(test_db)
    chat = Chat(id=1, user_id="user_123", title="Test Chat", created_at=datetime.now())

    # Act
    created_chat = repo.create(chat)

    # Assert
    assert created_chat.id == chat.id
    assert created_chat.user_id == chat.user_id
    assert created_chat.title == chat.title


def test_get_chat(test_db):
    # Arrange
    repo = ChatRepository(test_db)
    chat = Chat(id=1, user_id="user_123", title="Test Chat", created_at=datetime.now())
    repo.create(chat)

    # Act
    retrieved_chat = repo.get_by_id(chat.id)

    # Assert
    assert retrieved_chat is not None
    assert retrieved_chat.id == chat.id
