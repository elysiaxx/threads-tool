from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    role: str = "user"
    plan: str = "free"
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
