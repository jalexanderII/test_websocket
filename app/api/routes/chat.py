from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config.dependencies import get_chat_service
from app.schemas.chat import Chat
from app.services.chat.service import ChatService


class DeleteChatsRequest(BaseModel):
    chat_ids: List[int]


chat_router = APIRouter()


@chat_router.post("/chats", response_model=Chat)
async def create_chat(
    user_id: int,
    chat_service: ChatService = Depends(get_chat_service),
):
    return await chat_service.create_chat(user_id)


@chat_router.get("/chats/{chat_id}", response_model=Chat)
async def get_chat(
    chat_id: int,
    chat_service: ChatService = Depends(get_chat_service),
):
    chat = await chat_service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@chat_router.get("/users/{user_id}/chats", response_model=List[Chat])
async def get_user_chats(
    user_id: int,
    chat_service: ChatService = Depends(get_chat_service),
):
    return await chat_service.get_user_chats(user_id)


@chat_router.post("/chats/batch-delete", status_code=200)
async def delete_chats(
    request: DeleteChatsRequest,
    chat_service: ChatService = Depends(get_chat_service),
):
    await chat_service.delete_chats(request.chat_ids)
    return {"status": "success", "deleted_count": len(request.chat_ids)}


@chat_router.delete("/users/{user_id}/chats/empty")
async def delete_empty_chats(
    user_id: int,
    chat_service: ChatService = Depends(get_chat_service),
):
    """Delete all empty chats for a user."""
    deleted_count = await chat_service.delete_empty_chats(user_id)
    return {"deleted_count": deleted_count}
