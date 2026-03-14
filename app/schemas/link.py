from pydantic import BaseModel, HttpUrl, Field, field_validator
from datetime import datetime
from typing import Optional


class LinkBase(BaseModel):
    """Базовая схема ссылки"""
    original_url: HttpUrl


class LinkCreate(LinkBase):
    """Схема для создания ссылки"""
    custom_alias: Optional[str] = Field(None, min_length=3, max_length=20)
    expires_at: Optional[datetime] = None
    
    @field_validator('custom_alias')
    @classmethod
    def validate_custom_alias(cls, v):
        if v:
            # Проверка на допустимые символы
            if not v.replace('-', '').replace('_', '').isalnum():
                raise ValueError('Custom alias can only contain letters, numbers, hyphens and underscores')
        return v


class LinkUpdate(BaseModel):
    """Схема для обновления ссылки"""
    original_url: HttpUrl


class LinkResponse(BaseModel):
    """Схема ответа с информацией о ссылке"""
    id: int
    original_url: str
    short_code: str
    short_url: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    click_count: int
    is_custom: bool
    user_id: Optional[int] = None
    last_accessed: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class LinkStats(BaseModel):
    """Схема статистики ссылки"""
    short_code: str
    original_url: str
    created_at: datetime
    click_count: int
    last_accessed: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    days_active: int
    avg_clicks_per_day: float


class ExpiredLink(BaseModel):
    """Схема истекшей ссылки"""
    id: int
    short_code: str
    original_url: str
    expires_at: datetime
    click_count: int
    days_expired: int
    
    class Config:
        from_attributes = True
