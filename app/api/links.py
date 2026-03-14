from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.auth import (
    get_current_admin_user,
    get_current_user,
    get_current_user_optional,
)
from app.config import get_settings
from app.database import get_db
from app.models.link import Link
from app.models.user import User
from app.schemas.link import (
    ExpiredLink,
    LinkCreate,
    LinkResponse,
    LinkStats,
    LinkUpdate,
)
from app.services.cache_service import cache_service
from app.services.link_service import link_service

settings = get_settings()
router = APIRouter()


def create_link_response(link: Link) -> dict:
    """Создать ответ с информацией о ссылке"""
    return {
        "id": link.id,
        "original_url": link.original_url,
        "short_code": link.short_code,
        "short_url": f"{settings.BASE_URL}/{link.short_code}",
        "created_at": link.created_at,
        "expires_at": link.expires_at,
        "click_count": link.click_count,
        "is_custom": link.is_custom,
        "user_id": link.user_id,
        "last_accessed": link.last_accessed,
    }


@router.post(
    "/shorten",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_short_link(
    link_data: LinkCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Создать короткую ссылку.

    Публичный доступ; авторизованный пользователь становится владельцем.
    """
    user_id = current_user.id if current_user else None
    link = link_service.create_link(db, link_data, user_id)
    return create_link_response(link)


# Маршруты с фиксированными путями — обязательно ДО /{short_code}

@router.get("/search", response_model=List[LinkResponse])
def search_links(
    original_url: str = Query(..., description="URL для поиска"),
    db: Session = Depends(get_db),
):
    """Поиск ссылок по оригинальному URL"""
    links = link_service.search_by_original_url(db, original_url)
    return [create_link_response(link) for link in links]


@router.get("/my-links", response_model=List[LinkResponse])
def get_my_links(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Получить все ссылки текущего пользователя"""
    links = link_service.get_user_links(
        db, current_user.id, skip, limit
    )
    return [create_link_response(link) for link in links]


@router.get("/expired", response_model=List[ExpiredLink])
def get_expired_links(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Получить все истекшие ссылки пользователя"""
    links = link_service.get_expired_links(db, current_user.id)
    expired_links = []
    for link in links:
        days_expired = (datetime.now(timezone.utc) - link.expires_at).days
        expired_links.append({
            "id": link.id,
            "short_code": link.short_code,
            "original_url": link.original_url,
            "expires_at": link.expires_at,
            "click_count": link.click_count,
            "days_expired": days_expired,
        })
    return expired_links


# Маршруты с параметром /{short_code}

@router.get("/{short_code}/stats", response_model=LinkStats)
async def get_link_stats(
    short_code: str,
    db: Session = Depends(get_db),
):
    """Получить статистику ссылки"""
    cached_stats = await cache_service.get_stats(short_code)
    if cached_stats:
        return cached_stats

    link = await link_service.get_link_by_short_code(
        db, short_code, use_cache=False
    )
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )

    days_active = (datetime.now(timezone.utc) - link.created_at).days or 1
    avg_clicks = (
        link.click_count / days_active
        if days_active > 0
        else link.click_count
    )
    stats = {
        "short_code": link.short_code,
        "original_url": link.original_url,
        "created_at": link.created_at,
        "click_count": link.click_count,
        "last_accessed": link.last_accessed,
        "expires_at": link.expires_at,
        "days_active": days_active,
        "avg_clicks_per_day": round(avg_clicks, 2),
    }
    await cache_service.set_stats(short_code, stats)
    return stats


@router.get("/{short_code}", response_model=LinkResponse)
async def get_link_info(
    short_code: str,
    db: Session = Depends(get_db),
):
    """Получить информацию о ссылке"""
    link = await link_service.get_link_by_short_code(db, short_code)
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )
    return create_link_response(link)


@router.put("/{short_code}", response_model=LinkResponse)
async def update_link(
    short_code: str,
    link_data: LinkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Обновить оригинальный URL ссылки.

    Требует аутентификации и права владения.
    """
    link = await link_service.get_link_by_short_code(
        db, short_code, use_cache=False
    )
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )
    if link.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this link",
        )
    updated_link = await link_service.update_link(db, link, link_data)
    return create_link_response(updated_link)


@router.delete("/cleanup-inactive")
async def cleanup_inactive_links(
    days: int = Query(30, ge=1, description="Дни бездействия"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Удалить неактивные ссылки (только для администраторов).

    Удаляет ссылки, не использовавшиеся указанное количество дней.
    """
    deleted_count = link_service.delete_inactive_links(db, days)
    return {
        "deleted_count": deleted_count,
        "message": (
            f"Deleted {deleted_count} inactive links "
            f"older than {days} days"
        ),
    }


@router.delete("/{short_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    short_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Удалить ссылку.

    Требует аутентификации и права владения.
    """
    link = await link_service.get_link_by_short_code(
        db, short_code, use_cache=False
    )
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )
    if link.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this link",
        )
    await link_service.delete_link(db, link)
    return None


async def redirect_to_original(
    short_code: str,
    db: Session = Depends(get_db),
):
    """
    Перенаправление на оригинальный URL.

    Регистрируется в main.py как GET /{short_code}.
    """
    link = await link_service.get_link_by_short_code(db, short_code)
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )
    await link_service.increment_click_count(db, link.short_code)
    return RedirectResponse(
        url=link.original_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
