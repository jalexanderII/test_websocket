from fastapi import Depends
from sqlalchemy.orm import (
    Session,
)

from app.config.database import get_db
from app.services.chat.repository import ChatRepository
from app.services.chat.service import ChatService


def get_chat_repository(db: Session = Depends(get_db)) -> ChatRepository:
    return ChatRepository(db)


def get_chat_service(
    repository: ChatRepository = Depends(get_chat_repository),
) -> ChatService:
    return ChatService(repository)
