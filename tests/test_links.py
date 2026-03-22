"""Functional tests for links endpoints."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.link import Link
from app.services.cache_service import cache_service
from tests.conftest import _naive_utcnow

_BASE = "/api/links"
_BEARER = "Bearer "


def _auth(token: str) -> dict:
    return {"Authorization": f"{_BEARER}{token}"}


class TestCreateShortLink:
    _url = f"{_BASE}/shorten"
    _original = "https://example.com"

    def test_create_anonymous(self, client):
        response = client.post(self._url, json={
            "original_url": self._original,
        })
        assert response.status_code == 201
        data = response.json()
        assert data["original_url"].startswith(self._original)
        assert data["short_code"]
        assert data["user_id"] is None
        assert data["is_custom"] is False

    def test_create_authenticated(
        self, client, test_user, user_token
    ):
        response = client.post(
            self._url,
            json={"original_url": self._original},
            headers=_auth(user_token),
        )
        assert response.status_code == 201
        assert response.json()["user_id"] == test_user.id

    def test_create_with_custom_alias(self, client):
        response = client.post(self._url, json={
            "original_url": self._original,
            "custom_alias": "my-alias",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["short_code"] == "my-alias"
        assert data["is_custom"] is True

    def test_create_duplicate_custom_alias(
        self, client, test_link
    ):
        response = client.post(self._url, json={
            "original_url": self._original,
            "custom_alias": test_link.short_code,
        })
        assert response.status_code == 409

    def test_create_invalid_url(self, client):
        response = client.post(self._url, json={
            "original_url": "not-a-url",
        })
        assert response.status_code == 422

    def test_create_with_custom_expiry(self, client):
        expires = (
            _naive_utcnow() + timedelta(days=7)
        ).isoformat()
        response = client.post(self._url, json={
            "original_url": self._original,
            "expires_at": expires,
        })
        assert response.status_code == 201
        assert response.json()["expires_at"] is not None

    def test_create_invalid_custom_alias_chars(self, client):
        response = client.post(self._url, json={
            "original_url": self._original,
            "custom_alias": "invalid alias!",
        })
        assert response.status_code == 422

    def test_create_custom_alias_too_short(self, client):
        response = client.post(self._url, json={
            "original_url": self._original,
            "custom_alias": "ab",
        })
        assert response.status_code == 422

    def test_response_contains_short_url(self, client):
        response = client.post(self._url, json={
            "original_url": self._original,
        })
        assert response.status_code == 201
        data = response.json()
        assert "short_url" in data
        assert data["short_code"] in data["short_url"]

    def test_response_contains_click_count(self, client):
        response = client.post(self._url, json={
            "original_url": self._original,
        })
        assert response.status_code == 201
        assert response.json()["click_count"] == 0


class TestGetLinkInfo:
    def test_get_existing_link(self, client, test_link):
        response = client.get(
            f"{_BASE}/{test_link.short_code}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["short_code"] == test_link.short_code
        assert data["original_url"] == test_link.original_url

    def test_get_nonexistent_link(self, client):
        response = client.get(f"{_BASE}/doesnotexist")
        assert response.status_code == 404

    def test_get_link_returns_all_fields(
        self, client, test_link
    ):
        response = client.get(
            f"{_BASE}/{test_link.short_code}"
        )
        data = response.json()
        expected = {
            "id", "original_url", "short_code", "short_url",
            "created_at", "expires_at", "click_count",
            "is_custom", "user_id", "last_accessed",
        }
        assert expected.issubset(data.keys())


class TestRedirect:
    def test_redirect_existing_link(self, client, test_link):
        response = client.get(
            f"/{test_link.short_code}",
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert response.headers["location"] == (
            test_link.original_url
        )

    def test_redirect_nonexistent_link(self, client):
        response = client.get(
            "/nonexistentcode",
            follow_redirects=False,
        )
        assert response.status_code == 404

    def test_redirect_increments_popular(
        self, client, test_link
    ):
        client.get(
            f"/{test_link.short_code}",
            follow_redirects=False,
        )
        cache_service.increment_popular.assert_called_once()

    def test_redirect_expired_link(
        self, client, db_session, test_user
    ):
        expired = Link(
            original_url="https://expired.example.com",
            short_code="expiredlnk",
            user_id=test_user.id,
            is_custom=False,
            expires_at=(
                _naive_utcnow() - timedelta(days=1)
            ),
        )
        db_session.add(expired)
        db_session.commit()
        response = client.get(
            "/expiredlnk",
            follow_redirects=False,
        )
        assert response.status_code == 404


class TestUpdateLink:
    _new_url = "https://updated-example.com"

    def test_update_by_owner(
        self, client, test_link, user_token
    ):
        response = client.put(
            f"{_BASE}/{test_link.short_code}",
            json={"original_url": self._new_url},
            headers=_auth(user_token),
        )
        assert response.status_code == 200
        assert response.json()["original_url"].startswith(
            self._new_url
        )

    def test_update_by_admin(
        self, client, test_link, admin_token
    ):
        response = client.put(
            f"{_BASE}/{test_link.short_code}",
            json={"original_url": self._new_url},
            headers=_auth(admin_token),
        )
        assert response.status_code == 200

    def test_update_by_non_owner_forbidden(
        self,
        client,
        test_link,
        second_user_token,
    ):
        response = client.put(
            f"{_BASE}/{test_link.short_code}",
            json={"original_url": self._new_url},
            headers=_auth(second_user_token),
        )
        assert response.status_code == 403

    def test_update_nonexistent_link(
        self, client, user_token
    ):
        response = client.put(
            f"{_BASE}/nonexistent",
            json={"original_url": self._new_url},
            headers=_auth(user_token),
        )
        assert response.status_code == 404

    def test_update_no_auth(self, client, test_link):
        response = client.put(
            f"{_BASE}/{test_link.short_code}",
            json={"original_url": self._new_url},
        )
        assert response.status_code == 401

    def test_update_invalid_url(
        self, client, test_link, user_token
    ):
        response = client.put(
            f"{_BASE}/{test_link.short_code}",
            json={"original_url": "not-a-url"},
            headers=_auth(user_token),
        )
        assert response.status_code == 422

    def test_update_cache_invalidated(
        self, client, test_link, user_token
    ):
        client.put(
            f"{_BASE}/{test_link.short_code}",
            json={"original_url": self._new_url},
            headers=_auth(user_token),
        )
        cache_service.delete_link.assert_called()


class TestDeleteLink:
    def test_delete_by_owner(
        self, client, test_link, user_token
    ):
        response = client.delete(
            f"{_BASE}/{test_link.short_code}",
            headers=_auth(user_token),
        )
        assert response.status_code == 204

    def test_delete_by_admin(
        self, client, test_link, admin_token
    ):
        response = client.delete(
            f"{_BASE}/{test_link.short_code}",
            headers=_auth(admin_token),
        )
        assert response.status_code == 204

    def test_delete_by_non_owner_forbidden(
        self,
        client,
        test_link,
        second_user_token,
    ):
        response = client.delete(
            f"{_BASE}/{test_link.short_code}",
            headers=_auth(second_user_token),
        )
        assert response.status_code == 403

    def test_delete_nonexistent_link(
        self, client, user_token
    ):
        response = client.delete(
            f"{_BASE}/nonexistent",
            headers=_auth(user_token),
        )
        assert response.status_code == 404

    def test_delete_no_auth(self, client, test_link):
        response = client.delete(
            f"{_BASE}/{test_link.short_code}"
        )
        assert response.status_code == 401

    def test_delete_removes_link(
        self, client, test_link, user_token
    ):
        client.delete(
            f"{_BASE}/{test_link.short_code}",
            headers=_auth(user_token),
        )
        check = client.get(f"{_BASE}/{test_link.short_code}")
        assert check.status_code == 404


class TestSearchLinks:
    def test_search_returns_results(
        self, client, test_link
    ):
        response = client.get(
            f"{_BASE}/search",
            params={"original_url": "example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_search_no_results(self, client):
        response = client.get(
            f"{_BASE}/search",
            params={"original_url": "xyz-nonexistent-99.io"},
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_search_missing_param(self, client):
        response = client.get(f"{_BASE}/search")
        assert response.status_code == 422

    def test_search_case_insensitive(
        self, client, test_link
    ):
        response = client.get(
            f"{_BASE}/search",
            params={"original_url": "EXAMPLE.COM"},
        )
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_search_partial_url(self, client, test_link):
        response = client.get(
            f"{_BASE}/search",
            params={"original_url": "example"},
        )
        assert response.status_code == 200
        assert len(response.json()) >= 1


class TestMyLinks:
    def test_get_my_links_empty(self, client, user_token):
        response = client.get(
            f"{_BASE}/my-links",
            headers=_auth(user_token),
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_get_my_links_with_data(
        self, client, test_link, user_token
    ):
        response = client.get(
            f"{_BASE}/my-links",
            headers=_auth(user_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["short_code"] == test_link.short_code

    def test_get_my_links_no_auth(self, client):
        response = client.get(f"{_BASE}/my-links")
        assert response.status_code == 401

    def test_get_my_links_pagination(
        self, client, db_session, test_user, user_token
    ):
        for i in range(5):
            db_session.add(Link(
                original_url=f"https://site{i}.com",
                short_code=f"pg{i:04d}",
                user_id=test_user.id,
                is_custom=False,
                expires_at=(
                    _naive_utcnow() + timedelta(days=30)
                ),
            ))
        db_session.commit()

        response = client.get(
            f"{_BASE}/my-links",
            params={"skip": 0, "limit": 3},
            headers=_auth(user_token),
        )
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_get_my_links_skip(
        self, client, db_session, test_user, user_token
    ):
        for i in range(4):
            db_session.add(Link(
                original_url=f"https://skip{i}.com",
                short_code=f"sk{i:04d}",
                user_id=test_user.id,
                is_custom=False,
                expires_at=(
                    _naive_utcnow() + timedelta(days=30)
                ),
            ))
        db_session.commit()

        response = client.get(
            f"{_BASE}/my-links",
            params={"skip": 2, "limit": 10},
            headers=_auth(user_token),
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_get_my_links_only_own(
        self,
        client,
        db_session,
        test_user,
        second_user,
        user_token,
    ):
        db_session.add(Link(
            original_url="https://otheruser.com",
            short_code="other1",
            user_id=second_user.id,
            is_custom=False,
            expires_at=(
                _naive_utcnow() + timedelta(days=30)
            ),
        ))
        db_session.add(Link(
            original_url="https://mylink.com",
            short_code="mine1",
            user_id=test_user.id,
            is_custom=False,
            expires_at=(
                _naive_utcnow() + timedelta(days=30)
            ),
        ))
        db_session.commit()

        response = client.get(
            f"{_BASE}/my-links",
            headers=_auth(user_token),
        )
        assert response.status_code == 200
        data = response.json()
        user_ids = {item["user_id"] for item in data}
        assert user_ids == {test_user.id}


class TestExpiredLinks:
    def test_get_expired_empty(self, client, user_token):
        response = client.get(
            f"{_BASE}/expired",
            headers=_auth(user_token),
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_get_expired_with_data(
        self, client, db_session, test_user, user_token
    ):
        db_session.add(Link(
            original_url="https://old.example.com",
            short_code="oldlnk1",
            user_id=test_user.id,
            is_custom=False,
            expires_at=(
                _naive_utcnow() - timedelta(days=5)
            ),
        ))
        db_session.commit()

        response = client.get(
            f"{_BASE}/expired",
            headers=_auth(user_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["short_code"] == "oldlnk1"
        assert data[0]["days_expired"] >= 5

    def test_get_expired_no_auth(self, client):
        response = client.get(f"{_BASE}/expired")
        assert response.status_code == 401

    def test_active_link_not_in_expired(
        self, client, test_link, user_token
    ):
        response = client.get(
            f"{_BASE}/expired",
            headers=_auth(user_token),
        )
        assert response.status_code == 200
        short_codes = [
            item["short_code"] for item in response.json()
        ]
        assert test_link.short_code not in short_codes

    def test_expired_response_fields(
        self, client, db_session, test_user, user_token
    ):
        db_session.add(Link(
            original_url="https://exp2.example.com",
            short_code="exp2lnk",
            user_id=test_user.id,
            is_custom=False,
            expires_at=(
                _naive_utcnow() - timedelta(days=2)
            ),
        ))
        db_session.commit()

        response = client.get(
            f"{_BASE}/expired",
            headers=_auth(user_token),
        )
        item = response.json()[0]
        assert "days_expired" in item
        assert "expires_at" in item
        assert "click_count" in item


class TestLinkStats:
    def test_get_stats_existing(self, client, test_link):
        response = client.get(
            f"{_BASE}/{test_link.short_code}/stats"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["short_code"] == test_link.short_code
        assert "click_count" in data
        assert "avg_clicks_per_day" in data
        assert "days_active" in data

    def test_get_stats_nonexistent(self, client):
        response = client.get(f"{_BASE}/nonexistent/stats")
        assert response.status_code == 404

    def test_get_stats_from_cache(self, client, test_link):
        cached = {
            "short_code": test_link.short_code,
            "original_url": test_link.original_url,
            "created_at": (
                _naive_utcnow().isoformat()
            ),
            "click_count": 42,
            "last_accessed": None,
            "expires_at": None,
            "days_active": 1,
            "avg_clicks_per_day": 42.0,
        }
        cache_service.get_stats = AsyncMock(
            return_value=cached
        )
        response = client.get(
            f"{_BASE}/{test_link.short_code}/stats"
        )
        assert response.status_code == 200
        assert response.json()["click_count"] == 42

    def test_stats_days_active_positive(
        self, client, test_link
    ):
        response = client.get(
            f"{_BASE}/{test_link.short_code}/stats"
        )
        data = response.json()
        assert data["days_active"] >= 1

    def test_stats_avg_clicks_non_negative(
        self, client, test_link
    ):
        response = client.get(
            f"{_BASE}/{test_link.short_code}/stats"
        )
        assert response.json()["avg_clicks_per_day"] >= 0.0


class TestCleanupInactiveLinks:
    def test_cleanup_by_admin(self, client, admin_token):
        response = client.delete(
            f"{_BASE}/cleanup-inactive",
            headers=_auth(admin_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert "deleted_count" in data
        assert "message" in data

    def test_cleanup_by_non_admin(
        self, client, user_token
    ):
        response = client.delete(
            f"{_BASE}/cleanup-inactive",
            headers=_auth(user_token),
        )
        assert response.status_code == 403

    def test_cleanup_no_auth(self, client):
        response = client.delete(
            f"{_BASE}/cleanup-inactive"
        )
        assert response.status_code == 401

    def test_cleanup_deletes_inactive_links(
        self, client, db_session, test_user, admin_token
    ):
        old_date = (
            _naive_utcnow() - timedelta(days=60)
        )
        db_session.add(Link(
            original_url="https://inactive.example.com",
            short_code="inactive1",
            user_id=test_user.id,
            is_custom=False,
            last_accessed=old_date,
            expires_at=(
                _naive_utcnow() + timedelta(days=365)
            ),
        ))
        db_session.commit()

        response = client.delete(
            f"{_BASE}/cleanup-inactive",
            params={"days": 30},
            headers=_auth(admin_token),
        )
        assert response.status_code == 200
        assert response.json()["deleted_count"] >= 1

    def test_cleanup_custom_days_param(
        self, client, admin_token
    ):
        response = client.delete(
            f"{_BASE}/cleanup-inactive",
            params={"days": 7},
            headers=_auth(admin_token),
        )
        assert response.status_code == 200

    def test_cleanup_invalid_days_param(
        self, client, admin_token
    ):
        response = client.delete(
            f"{_BASE}/cleanup-inactive",
            params={"days": 0},
            headers=_auth(admin_token),
        )
        assert response.status_code == 422
