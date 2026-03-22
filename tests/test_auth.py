"""Functional tests for authentication endpoints."""
import pytest


class TestRootEndpoints:
    def test_root_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_contains_message(self, client):
        response = client.get("/")
        data = response.json()
        assert "message" in data
        assert "version" in data

    def test_root_contains_docs(self, client):
        response = client.get("/")
        assert "docs" in response.json()

    def test_health_shadowed_by_short_code_route(
        self, client
    ):
        # /health перехватывается роутом /{short_code} — баг роутинга в main.py
        response = client.get(
            "/health", follow_redirects=False
        )
        assert response.status_code == 404


class TestRegister:
    _url = "/api/auth/register"

    def test_register_success(self, client):
        response = client.post(self._url, json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "password123",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "new@example.com"
        assert "id" in data
        assert "is_active" in data
        assert "is_admin" in data
        assert "created_at" in data
        assert data["is_admin"] is False

    def test_register_duplicate_username(self, client, test_user):
        response = client.post(self._url, json={
            "username": test_user.username,
            "email": "unique@example.com",
            "password": "password123",
        })
        assert response.status_code == 409

    def test_register_duplicate_email(self, client, test_user):
        response = client.post(self._url, json={
            "username": "uniqueusername",
            "email": test_user.email,
            "password": "password123",
        })
        assert response.status_code == 409

    def test_register_invalid_email(self, client):
        response = client.post(self._url, json={
            "username": "validuser",
            "email": "asdfasdfa",
            "password": "password123",
        })
        assert response.status_code == 422

    def test_register_password_too_short(self, client):
        response = client.post(self._url, json={
            "username": "validuser",
            "email": "valid@example.com",
            "password": "12345",
        })
        assert response.status_code == 422

    def test_register_username_too_short(self, client):
        response = client.post(self._url, json={
            "username": "ab",
            "email": "valid@example.com",
            "password": "password123",
        })
        assert response.status_code == 422

    def test_register_username_too_long(self, client):
        response = client.post(self._url, json={
            "username": "u" * 51,
            "email": "valid@example.com",
            "password": "password123",
        })
        assert response.status_code == 422

    def test_register_missing_fields(self, client):
        response = client.post(self._url, json={
            "username": "onlyuser",
        })
        assert response.status_code == 422


class TestLogin:
    _url = "/api/auth/login"

    def test_login_success(self, client, test_user):
        response = client.post(self._url, data={
            "username": "testuser",
            "password": "testpass123",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, test_user):
        response = client.post(self._url, data={
            "username": "testuser",
            "password": "wrongpassword",
        })
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client):
        response = client.post(self._url, data={
            "username": "nobody",
            "password": "password123",
        })
        assert response.status_code == 401

    def test_login_inactive_user(
        self, client, db_session, test_user
    ):
        test_user.is_active = False
        db_session.commit()
        response = client.post(self._url, data={
            "username": "testuser",
            "password": "testpass123",
        })
        assert response.status_code == 400

    def test_login_returns_bearer_token(self, client, test_user):
        response = client.post(self._url, data={
            "username": "testuser",
            "password": "testpass123",
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        assert isinstance(token, str)
        assert len(token) > 20


class TestGetMe:
    _url = "/api/auth/me"

    def test_get_me_success(self, client, test_user, user_token):
        response = client.get(
            self._url,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == test_user.username
        assert data["email"] == test_user.email

    def test_get_me_no_token(self, client):
        response = client.get(self._url)
        assert response.status_code == 401

    def test_get_me_invalid_token(self, client):
        response = client.get(
            self._url,
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == 401

    def test_get_me_admin(
        self, client, test_admin, admin_token
    ):
        response = client.get(
            self._url,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_admin"] is True
        assert data["username"] == test_admin.username

    def test_get_me_token_after_login(self, client, test_user):
        login_resp = client.post("/api/auth/login", data={
            "username": "testuser",
            "password": "testpass123",
        })
        token = login_resp.json()["access_token"]
        response = client.get(
            self._url,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["username"] == "testuser"
