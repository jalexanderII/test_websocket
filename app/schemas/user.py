from datetime import UTC, datetime

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    id: int | None = None
    username: str
    email: EmailStr
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
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
