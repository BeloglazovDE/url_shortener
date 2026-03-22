"""Unit tests for CacheService and related helpers."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cache_service import (
    CacheService,
    close_redis,
    get_redis,
)


@pytest.fixture()
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    r.zincrby = AsyncMock()
    r.zrevrange = AsyncMock(return_value=["code1", "code2"])
    return r


@pytest.fixture()
def svc(mock_redis):
    service = CacheService()
    service.redis = mock_redis
    return service


class TestGetRedis:
    @pytest.mark.asyncio
    async def test_get_redis_creates_client(self):
        import app.services.cache_service as cs

        original = cs.redis_client
        cs.redis_client = None
        try:
            with patch(
                "app.services.cache_service.redis.from_url",
                return_value=AsyncMock(),
            ) as mock_from_url:
                client = await get_redis()
                mock_from_url.assert_called_once()
                assert client is not None
        finally:
            cs.redis_client = original

    @pytest.mark.asyncio
    async def test_get_redis_returns_existing(self):
        import app.services.cache_service as cs

        fake = AsyncMock()
        original = cs.redis_client
        cs.redis_client = fake
        try:
            client = await get_redis()
            assert client is fake
        finally:
            cs.redis_client = original


class TestCloseRedis:
    @pytest.mark.asyncio
    async def test_close_redis_calls_close(self):
        import app.services.cache_service as cs

        fake = AsyncMock()
        original = cs.redis_client
        cs.redis_client = fake
        try:
            await close_redis()
            fake.close.assert_called_once()
        finally:
            cs.redis_client = original

    @pytest.mark.asyncio
    async def test_close_redis_no_client(self):
        import app.services.cache_service as cs

        original = cs.redis_client
        cs.redis_client = None
        try:
            await close_redis()
        finally:
            cs.redis_client = original


class TestCacheServiceGetClient:
    @pytest.mark.asyncio
    async def test_get_client_initializes_if_none(
        self, mock_redis
    ):
        svc = CacheService()
        svc.redis = None
        with patch(
            "app.services.cache_service.get_redis",
            new=AsyncMock(return_value=mock_redis),
        ):
            client = await svc.get_client()
            assert client is mock_redis

    @pytest.mark.asyncio
    async def test_get_client_returns_existing(
        self, svc, mock_redis
    ):
        client = await svc.get_client()
        assert client is mock_redis


class TestCacheServiceGetLink:
    @pytest.mark.asyncio
    async def test_get_link_returns_none_on_miss(
        self, svc, mock_redis
    ):
        mock_redis.get.return_value = None
        result = await svc.get_link("abc123")
        assert result is None
        mock_redis.get.assert_called_once_with("link:abc123")

    @pytest.mark.asyncio
    async def test_get_link_returns_dict_on_hit(
        self, svc, mock_redis
    ):
        payload = {"original_url": "https://example.com"}
        mock_redis.get.return_value = json.dumps(payload)
        result = await svc.get_link("abc123")
        assert result == payload


class TestCacheServiceSetLink:
    @pytest.mark.asyncio
    async def test_set_link_calls_setex(
        self, svc, mock_redis
    ):
        data = {"original_url": "https://example.com"}
        await svc.set_link("abc123", data, ttl=300)
        mock_redis.setex.assert_called_once_with(
            "link:abc123",
            300,
            json.dumps(data, default=str),
        )

    @pytest.mark.asyncio
    async def test_set_link_uses_settings_ttl(
        self, svc, mock_redis
    ):
        data = {"original_url": "https://example.com"}
        await svc.set_link("abc123", data)
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args[0]
        assert args[0] == "link:abc123"


class TestCacheServiceDeleteLink:
    @pytest.mark.asyncio
    async def test_delete_link_removes_both_keys(
        self, svc, mock_redis
    ):
        await svc.delete_link("abc123")
        calls = [c[0][0] for c in mock_redis.delete.call_args_list]
        assert "link:abc123" in calls
        assert "stats:abc123" in calls


class TestCacheServiceGetStats:
    @pytest.mark.asyncio
    async def test_get_stats_returns_none_on_miss(
        self, svc, mock_redis
    ):
        mock_redis.get.return_value = None
        result = await svc.get_stats("abc123")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_stats_returns_dict_on_hit(
        self, svc, mock_redis
    ):
        payload = {"click_count": 42}
        mock_redis.get.return_value = json.dumps(payload)
        result = await svc.get_stats("abc123")
        assert result == payload


class TestCacheServiceSetStats:
    @pytest.mark.asyncio
    async def test_set_stats_calls_setex(
        self, svc, mock_redis
    ):
        data = {"click_count": 5}
        await svc.set_stats("abc123", data)
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args[0]
        assert args[0] == "stats:abc123"
        assert json.loads(args[2]) == data


class TestCacheServiceIncrementPopular:
    @pytest.mark.asyncio
    async def test_increment_popular(self, svc, mock_redis):
        await svc.increment_popular("abc123")
        mock_redis.zincrby.assert_called_once_with(
            "popular_links", 1, "abc123"
        )


class TestCacheServiceGetPopularLinks:
    @pytest.mark.asyncio
    async def test_get_popular_links_default_limit(
        self, svc, mock_redis
    ):
        result = await svc.get_popular_links()
        mock_redis.zrevrange.assert_called_once_with(
            "popular_links", 0, 99
        )

    @pytest.mark.asyncio
    async def test_get_popular_links_custom_limit(
        self, svc, mock_redis
    ):
        await svc.get_popular_links(limit=5)
        mock_redis.zrevrange.assert_called_once_with(
            "popular_links", 0, 4
        )
