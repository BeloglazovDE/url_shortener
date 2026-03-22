from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models.link import Link
from app.models.user import User
from app.services.cache_service import cache_service
from app.utils.security import create_access_token, get_password_hash


class _NaiveDatetime(datetime):
    # SQLite не хранит timezone, поэтому патчим datetime.now
    # чтобы сравнения дат не падали с TypeError
    @classmethod
    def now(cls, tz=None):
        return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive_utcnow() -> datetime:
    # Чтобы не писать всю строку каждый раз
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def patch_datetime_for_sqlite(monkeypatch):
    # SQLite не хранит timezone — подменяем datetime в сервисах. Костыль, чтобы упростить тесты без postgres
    import app.api.links as _api_links
    import app.services.link_service as _link_svc

    monkeypatch.setattr(_link_svc, "datetime", _NaiveDatetime)
    monkeypatch.setattr(_api_links, "datetime", _NaiveDatetime)


@pytest.fixture(autouse=True)
def mock_cache():
    # Мокируем все методы Redis для каждого теста
    patches = [
        patch.object(
            cache_service,
            "get_link",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            cache_service, "set_link", new=AsyncMock()
        ),
        patch.object(
            cache_service, "delete_link", new=AsyncMock()
        ),
        patch.object(
            cache_service,
            "get_stats",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            cache_service, "set_stats", new=AsyncMock()
        ),
        patch.object(
            cache_service,
            "increment_popular",
            new=AsyncMock(),
        ),
        patch.object(
            cache_service,
            "get_popular_links",
            new=AsyncMock(return_value=[]),
        ),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def test_user(db_session):
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpass123"),
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def test_admin(db_session):
    admin = User(
        username="adminuser",
        email="admin@example.com",
        hashed_password=get_password_hash("adminpass123"),
        is_active=True,
        is_admin=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.fixture()
def second_user(db_session):
    user = User(
        username="seconduser",
        email="second@example.com",
        hashed_password=get_password_hash("secondpass123"),
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_token(username: str) -> str:
    settings = get_settings()
    return create_access_token(
        data={"sub": username},
        expires_delta=timedelta(minutes=30),
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


@pytest.fixture()
def user_token(test_user) -> str:
    return _make_token(test_user.username)


@pytest.fixture()
def admin_token(test_admin) -> str:
    return _make_token(test_admin.username)


@pytest.fixture()
def second_user_token(second_user) -> str:
    return _make_token(second_user.username)


@pytest.fixture()
def test_link(db_session, test_user):
    link = Link(
        original_url="https://example.com",
        short_code="abc123",
        user_id=test_user.id,
        is_custom=False,
        expires_at=_naive_utcnow() + timedelta(days=30),
    )
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)
    return link
