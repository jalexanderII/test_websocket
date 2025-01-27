from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from infrastructure.db.database import get_db
from application.services.chat_service import ChatService
from domain.entities.chat import Chat


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


@router.post("/chats/{chat_id}/abort")
async def abort_chat_response(
    chat_id: int, task_id: str, db: Session = Depends(get_db)
):
    chat_service = ChatService(db)
    await chat_service.abort_response(task_id)
    return {"status": "aborted", "task_id": task_id}
