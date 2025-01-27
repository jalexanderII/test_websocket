from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from infrastructure.db.database import get_db
from application.services.chat_service import ChatService
from domain.entities.chat import Chat


class DeleteChatsRequest(BaseModel):
    chat_ids: List[int]


router = APIRouter()


@router.post("/chats", response_model=Chat)
def create_chat(user_id: int, db: Session = Depends(get_db)):
    chat_service = ChatService(db)
    return chat_service.create_chat(user_id)


@router.get("/chats/{chat_id}", response_model=Chat)
def get_chat(chat_id: int, db: Session = Depends(get_db)):
    chat_service = ChatService(db)
    chat = chat_service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.get("/users/{user_id}/chats", response_model=List[Chat])
def get_user_chats(user_id: int, db: Session = Depends(get_db)):
    chat_service = ChatService(db)
    return chat_service.get_user_chats(user_id)


@router.post("/chats/batch-delete", status_code=200)
async def delete_chats(request: DeleteChatsRequest, db: Session = Depends(get_db)):
    chat_service = ChatService(db)
    chat_service.delete_chats(request.chat_ids)
    return {"status": "success", "deleted_count": len(request.chat_ids)}


@router.delete("/users/{user_id}/chats/empty")
def delete_empty_chats(user_id: int, db: Session = Depends(get_db)):
    """Delete all empty chats for a user."""
    chat_service = ChatService(db)
    deleted_count = chat_service.delete_empty_chats(user_id)
    return {"deleted_count": deleted_count}
