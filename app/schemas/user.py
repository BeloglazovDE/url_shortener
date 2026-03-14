from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    """Базовая схема пользователя"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr


class UserCreate(UserBase):
    """Схема для создания пользователя"""
    password: str = Field(..., min_length=6)



class UserResponse(UserBase):
    """Схема ответа с информацией о пользователе"""
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    """Схема JWT токена"""
    access_token: str
    token_type: str


class TokenData(BaseModel):
    """Данные из токена"""
    username: Optional[str] = None
