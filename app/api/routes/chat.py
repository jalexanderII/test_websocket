from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.schemas.chat import Chat
from app.services.chat.service import ChatService


class DeleteChatsRequest(BaseModel):
    chat_ids: List[int]


chat_router = APIRouter()


@chat_router.post("/chats", response_model=Chat)
async def create_chat(user_id: int, db: Session = Depends(get_db)):
    chat_service = ChatService(db)
    return await chat_service.create_chat(user_id)


@chat_router.get("/chats/{chat_id}", response_model=Chat)
async def get_chat(chat_id: int, db: Session = Depends(get_db)):
    chat_service = ChatService(db)
    chat = await chat_service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@chat_router.get("/users/{user_id}/chats", response_model=List[Chat])
async def get_user_chats(user_id: int, db: Session = Depends(get_db)):
    chat_service = ChatService(db)
    return await chat_service.get_user_chats(user_id)


@chat_router.post("/chats/batch-delete", status_code=200)
async def delete_chats(request: DeleteChatsRequest, db: Session = Depends(get_db)):
    chat_service = ChatService(db)
    await chat_service.delete_chats(request.chat_ids)
    return {"status": "success", "deleted_count": len(request.chat_ids)}


@chat_router.delete("/users/{user_id}/chats/empty")
async def delete_empty_chats(user_id: int, db: Session = Depends(get_db)):
    """Delete all empty chats for a user."""
    chat_service = ChatService(db)
    deleted_count = await chat_service.delete_empty_chats(user_id)
    return {"deleted_count": deleted_count}
