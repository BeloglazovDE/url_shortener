from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Link(Base):
    """Модель короткой ссылки"""

    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    original_url: Mapped[str] = mapped_column(Text)
    short_code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
    last_accessed: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    owner: Mapped[Optional["User"]] = relationship(
        "User", back_populates="links"
    )

    def __repr__(self) -> str:
        return (
            f"<Link(id={self.id}, short_code='{self.short_code}')>"
        )

    def to_dict(self) -> dict:
        """Конвертация в словарь для кэширования"""
        return {
            "id": self.id,
            "original_url": self.original_url,
            "short_code": self.short_code,
            "user_id": self.user_id,
            "is_custom": self.is_custom,
            "click_count": self.click_count,
            "created_at": (
                self.created_at.isoformat()
                if self.created_at else None
            ),
            "updated_at": (
                self.updated_at.isoformat()
                if self.updated_at else None
            ),
            "last_accessed": (
                self.last_accessed.isoformat()
                if self.last_accessed else None
            ),
            "expires_at": (
                self.expires_at.isoformat()
                if self.expires_at else None
            ),
        }
