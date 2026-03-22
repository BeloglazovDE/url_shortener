"""Unit tests for utility functions."""
from datetime import timedelta

import pytest

from app.utils.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from app.utils.short_code import generate_short_code, is_valid_short_code

_SECRET = "test-secret-key"
_ALGO = "HS256"


class TestGenerateShortCode:
    def test_default_length(self):
        code = generate_short_code()
        assert len(code) == 6

    def test_custom_length(self):
        code = generate_short_code(10)
        assert len(code) == 10

    def test_single_char_length(self):
        code = generate_short_code(1)
        assert len(code) == 1

    def test_alphanumeric_only(self):
        for _ in range(50):
            code = generate_short_code()
            assert code.isalnum(), f"Non-alnum code: {code}"

    def test_uniqueness(self):
        codes = {generate_short_code() for _ in range(200)}
        assert len(codes) > 1

    def test_zero_length(self):
        code = generate_short_code(0)
        assert len(code) == 0


class TestIsValidShortCode:
    def test_valid_alphanumeric(self):
        assert is_valid_short_code("abc123") is True

    def test_valid_with_hyphen(self):
        assert is_valid_short_code("my-link") is True

    def test_valid_with_underscore(self):
        assert is_valid_short_code("my_link") is True

    def test_valid_min_length(self):
        assert is_valid_short_code("abc") is True

    def test_valid_max_length(self):
        assert is_valid_short_code("a" * 20) is True

    def test_invalid_too_short(self):
        assert is_valid_short_code("ab") is False

    def test_invalid_too_long(self):
        assert is_valid_short_code("a" * 21) is False

    def test_invalid_empty(self):
        assert is_valid_short_code("") is False

    def test_invalid_space(self):
        assert is_valid_short_code("my link") is False

    def test_invalid_special_chars(self):
        assert is_valid_short_code("link!!!") is False

    def test_invalid_dot(self):
        assert is_valid_short_code("my.link") is False

    def test_combined_valid_chars(self):
        assert is_valid_short_code("my-link_123") is True


class TestPasswordSecurity:
    def test_hash_differs_from_plain(self):
        hashed = get_password_hash("mysecret")
        assert hashed != "mysecret"

    def test_verify_correct_password(self):
        hashed = get_password_hash("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("mypassword")
        assert verify_password("wrongpass", hashed) is False

    def test_same_password_produces_different_hashes(self):
        h1 = get_password_hash("password")
        h2 = get_password_hash("password")
        assert h1 != h2

    def test_hash_format(self):
        hashed = get_password_hash("password")
        assert hashed.startswith("$2b$")


class TestJWT:
    def test_create_and_decode_token(self):
        token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=timedelta(minutes=30),
            secret_key=_SECRET,
            algorithm=_ALGO,
        )
        username = decode_access_token(token, _SECRET, _ALGO)
        assert username == "testuser"

    def test_decode_invalid_token(self):
        result = decode_access_token(
            "invalid.token.here", _SECRET, _ALGO
        )
        assert result is None

    def test_decode_with_wrong_secret(self):
        token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=timedelta(minutes=30),
            secret_key=_SECRET,
            algorithm=_ALGO,
        )
        result = decode_access_token(token, "wrong-secret", _ALGO)
        assert result is None

    def test_decode_expired_token(self):
        token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=timedelta(minutes=-1),
            secret_key=_SECRET,
            algorithm=_ALGO,
        )
        result = decode_access_token(token, _SECRET, _ALGO)
        assert result is None

    def test_token_contains_sub(self):
        token = create_access_token(
            data={"sub": "alice"},
            expires_delta=timedelta(hours=1),
            secret_key=_SECRET,
            algorithm=_ALGO,
        )
        username = decode_access_token(token, _SECRET, _ALGO)
        assert username == "alice"

    def test_empty_string_token(self):
        result = decode_access_token("", _SECRET, _ALGO)
        assert result is None
