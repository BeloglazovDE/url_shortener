"""Tests for main.py app setup and helper functions."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app, create_admin_user
from app.models.user import User
from app.utils.security import get_password_hash


@pytest.fixture()
def isolated_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def isolated_session(isolated_engine):
    Session = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=isolated_engine,
    )
    db = Session()
    try:
        yield db
    finally:
        db.close()
        isolated_engine.dispose()


class TestCreateAdminUser:
    def test_creates_admin_when_settings_present(
        self, isolated_session
    ):
        with patch(
            "app.main.SessionLocal",
            return_value=isolated_session,
        ), patch(
            "app.main.settings.ADMIN_USERNAME",
            "testadmin",
        ), patch(
            "app.main.settings.ADMIN_EMAIL",
            "testadmin@example.com",
        ), patch(
            "app.main.settings.ADMIN_PASSWORD",
            "adminpass123",
        ):
            create_admin_user()

        admin = isolated_session.query(User).filter(
            User.username == "testadmin"
        ).first()
        assert admin is not None
        assert admin.is_admin is True
        assert admin.email == "testadmin@example.com"

    def test_skips_if_admin_already_exists(
        self, isolated_session
    ):
        existing = User(
            username="existingadmin",
            email="exist@example.com",
            hashed_password=get_password_hash("pass"),
            is_active=True,
            is_admin=True,
        )
        isolated_session.add(existing)
        isolated_session.commit()

        call_count = {"add": 0}
        original_add = isolated_session.add

        def track_add(obj):
            if isinstance(obj, User):
                call_count["add"] += 1
            return original_add(obj)

        with patch(
            "app.main.SessionLocal",
            return_value=isolated_session,
        ), patch(
            "app.main.settings.ADMIN_USERNAME",
            "existingadmin",
        ), patch(
            "app.main.settings.ADMIN_EMAIL",
            "exist@example.com",
        ), patch(
            "app.main.settings.ADMIN_PASSWORD",
            "adminpass123",
        ), patch.object(
            isolated_session, "add", side_effect=track_add
        ):
            create_admin_user()

        assert call_count["add"] == 0

    def test_skips_if_no_settings(self, isolated_session):
        with patch(
            "app.main.SessionLocal",
            return_value=isolated_session,
        ), patch(
            "app.main.settings.ADMIN_USERNAME", None
        ), patch(
            "app.main.settings.ADMIN_EMAIL", None
        ), patch(
            "app.main.settings.ADMIN_PASSWORD", None
        ):
            create_admin_user()

        count = isolated_session.query(User).count()
        assert count == 0


class TestLifecycleEvents:
    def test_startup_calls_create_admin_user(self):
        with patch(
            "app.main.create_admin_user"
        ) as mock_create, patch(
            "app.main.close_redis", new=AsyncMock()
        ):
            with TestClient(app):
                mock_create.assert_called_once()

    def test_shutdown_calls_close_redis(self):
        close_mock = AsyncMock()
        with patch("app.main.create_admin_user"), patch(
            "app.main.close_redis", close_mock
        ):
            with TestClient(app):
                pass
            close_mock.assert_called_once()
