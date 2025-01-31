from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    id: Optional[int] = None
    username: str
    email: EmailStr
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True


class UserCreate(BaseModel):
    username: str
    email: EmailStr


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime
    is_active: bool
