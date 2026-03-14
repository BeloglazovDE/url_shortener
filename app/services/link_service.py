from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, update as sql_update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.link import Link
from app.schemas.link import LinkCreate, LinkUpdate
from app.services.cache_service import cache_service
from app.utils.short_code import generate_short_code, is_valid_short_code

settings = get_settings()


class LinkService:
    """Сервис для работы со ссылками"""
    
    @staticmethod
    def create_link(
        db: Session,
        link_data: LinkCreate,
        user_id: Optional[int] = None
    ) -> Link:
        """
        Создать короткую ссылку
        
        Args:
            db: сессия БД
            link_data: данные ссылки
            user_id: ID пользователя (опционально)
            
        Returns:
            Link: созданная ссылка
        """
        if link_data.custom_alias:
            short_code = link_data.custom_alias
            is_custom = True
            
            existing = db.query(Link).filter(Link.short_code == short_code).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Custom alias already exists"
                )
        else:
            is_custom = False
            max_attempts = 50
            
            for _ in range(max_attempts):
                short_code = generate_short_code(settings.SHORT_CODE_LENGTH)
                existing = db.query(Link).filter(Link.short_code == short_code).first()
                if not existing:
                    break
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate unique short code"
                )
        
        expires_at = link_data.expires_at or (
            datetime.now(timezone.utc) + timedelta(days=30)
        )

        link = Link(
            original_url=str(link_data.original_url),
            short_code=short_code,
            user_id=user_id,
            is_custom=is_custom,
            expires_at=expires_at,
        )
        
        db.add(link)
        db.commit()
        db.refresh(link)
        
        return link
    
    @staticmethod
    async def get_link_by_short_code(
        db: Session,
        short_code: str,
        use_cache: bool = True
    ) -> Optional[Link]:
        """
        Получить ссылку по короткому коду
        
        Args:
            db: сессия БД
            short_code: короткий код
            use_cache: использовать кэш
            
        Returns:
            Optional[Link]: ссылка или None
        """
        # Проверка кэша — возвращаем только original_url и short_code для чтения
        if use_cache:
            cached = await cache_service.get_link(short_code)
            if cached:
                expires_at_raw = cached.get("expires_at")
                if expires_at_raw:
                    expires_at = datetime.fromisoformat(expires_at_raw)
                    if expires_at < datetime.now(timezone.utc):
                        return None
                link = db.query(Link).filter(
                    Link.short_code == short_code
                ).first()
                return link

        # Запрос к БД, если не в кэше
        link = db.query(Link).filter(Link.short_code == short_code).first()

        if link:
            if link.expires_at and link.expires_at < datetime.now(timezone.utc):
                return None

            # Сохранение в кэш
            if use_cache:
                await cache_service.set_link(short_code, link.to_dict())

        return link
    
    @staticmethod
    async def increment_click_count(db: Session, short_code: str):
        """
        Увеличить счетчик переходов через прямой SQL UPDATE.

        Не зависит от того, привязан ли объект к сессии.

        Args:
            db: сессия БД
            short_code: короткий код ссылки
        """
        db.execute(
            sql_update(Link)
            .where(Link.short_code == short_code)
            .values(
                click_count=Link.click_count + 1,
                last_accessed=datetime.now(timezone.utc),
            )
        )
        db.commit()

        await cache_service.increment_popular(short_code)
        await cache_service.delete_link(short_code)
    
    @staticmethod
    async def update_link(
        db: Session,
        link: Link,
        link_data: LinkUpdate
    ) -> Link:
        """
        Обновить ссылку
        
        Args:
            db: сессия БД
            link: ссылка
            link_data: новые данные
            
        Returns:
            Link: обновленная ссылка
        """
        link.original_url = str(link_data.original_url)
        link.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(link)
        
        # Инвалидация кэша
        await cache_service.delete_link(link.short_code)
        
        return link
    
    @staticmethod
    async def delete_link(db: Session, link: Link):
        """
        Удалить ссылку
        
        Args:
            db: сессия БД
            link: ссылка
        """
        db.delete(link)
        db.commit()
        
        # Инвалидация кэша
        await cache_service.delete_link(link.short_code)
    
    @staticmethod
    def search_by_original_url(
        db: Session,
        original_url: str
    ) -> List[Link]:
        """
        Поиск ссылок по оригинальному URL
        
        Args:
            db: сессия БД
            original_url: оригинальный URL
            
        Returns:
            List[Link]: список найденных ссылок
        """
        return db.query(Link).filter(
            Link.original_url.ilike(f"%{original_url}%")
        ).all()
    
    @staticmethod
    def get_user_links(
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[Link]:
        """
        Получить все ссылки пользователя
        
        Args:
            db: сессия БД
            user_id: ID пользователя
            skip: смещение
            limit: лимит
            
        Returns:
            List[Link]: список ссылок
        """
        return db.query(Link).filter(
            Link.user_id == user_id
        ).offset(skip).limit(limit).all()
    
    @staticmethod
    def delete_inactive_links(
        db: Session,
        days: int = 30
    ) -> int:
        """
        Удалить неактивные ссылки
        
        Args:
            db: сессия БД
            days: количество дней неактивности
            
        Returns:
            int: количество удаленных ссылок
        """
        threshold_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        inactive_links = db.query(Link).filter(
            and_(
                Link.last_accessed < threshold_date,
                Link.last_accessed.isnot(None)
            )
        ).all()
        
        count = len(inactive_links)
        
        for link in inactive_links:
            db.delete(link)
        
        db.commit()
        
        return count
    
    @staticmethod
    def get_expired_links(db: Session, user_id: Optional[int] = None) -> List[Link]:
        """
        Получить истекшие ссылки
        
        Args:
            db: сессия БД
            user_id: ID пользователя (опционально)
            
        Returns:
            List[Link]: список истекших ссылок
        """
        query = db.query(Link).filter(
            and_(
                Link.expires_at.isnot(None),
                Link.expires_at < datetime.now(timezone.utc)
            )
        )
        
        if user_id:
            query = query.filter(Link.user_id == user_id)
        
        return query.all()


link_service = LinkService()
