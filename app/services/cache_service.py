import json
from typing import Optional
import redis.asyncio as redis
from app.config import get_settings

settings = get_settings()

# Redis клиент
redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Получить Redis клиент"""
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
    return redis_client


async def close_redis():
    """Закрыть Redis соединение"""
    global redis_client
    if redis_client:
        await redis_client.close()


class CacheService:
    """Сервис для работы с кэшем"""
    
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
    
    async def get_client(self) -> redis.Redis:
        """Получить Redis клиент"""
        if not self.redis:
            self.redis = await get_redis()
        return self.redis
    
    async def get_link(self, short_code: str) -> Optional[dict]:
        """
        Получить ссылку из кэша
        
        Args:
            short_code: короткий код
            
        Returns:
            Optional[dict]: данные ссылки или None
        """
        client = await self.get_client()
        cache_key = f"link:{short_code}"
        
        cached = await client.get(cache_key)
        if cached:
            return json.loads(cached)
        return None
    
    async def set_link(self, short_code: str, link_data: dict, ttl: int = None):
        """
        Сохранить ссылку в кэш
        
        Args:
            short_code: короткий код
            link_data: данные ссылки
            ttl: время жизни в секундах (по умолчанию из настроек)
        """
        client = await self.get_client()
        cache_key = f"link:{short_code}"
        
        if ttl is None:
            ttl = settings.CACHE_TTL
        
        await client.setex(
            cache_key,
            ttl,
            json.dumps(link_data, default=str)
        )
    
    async def delete_link(self, short_code: str):
        """
        Удалить ссылку из кэша
        
        Args:
            short_code: короткий код
        """
        client = await self.get_client()
        await client.delete(f"link:{short_code}")
        await client.delete(f"stats:{short_code}")
    
    async def get_stats(self, short_code: str) -> Optional[dict]:
        """
        Получить статистику из кэша
        
        Args:
            short_code: короткий код
            
        Returns:
            Optional[dict]: статистика или None
        """
        client = await self.get_client()
        cache_key = f"stats:{short_code}"
        
        cached = await client.get(cache_key)
        if cached:
            return json.loads(cached)
        return None
    
    async def set_stats(self, short_code: str, stats_data: dict):
        """
        Сохранить статистику в кэш
        
        Args:
            short_code: короткий код
            stats_data: данные статистики
        """
        client = await self.get_client()
        cache_key = f"stats:{short_code}"
        
        await client.setex(
            cache_key,
            settings.STATS_CACHE_TTL,
            json.dumps(stats_data, default=str)
        )
    
    async def increment_popular(self, short_code: str):
        """
        Увеличить счетчик популярности
        
        Args:
            short_code: короткий код
        """
        client = await self.get_client()
        await client.zincrby("popular_links", 1, short_code)
    
    async def get_popular_links(self, limit: int = 100) -> list:
        """
        Получить популярные ссылки
        
        Args:
            limit: количество ссылок
            
        Returns:
            list: список коротких кодов
        """
        client = await self.get_client()
        return await client.zrevrange("popular_links", 0, limit - 1)


# Глобальный экземпляр
cache_service = CacheService()
