from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Хеширование пароля"""
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: timedelta,
    secret_key: str,
    algorithm: str,
) -> str:
    """
    Создание JWT токена

    Args:
        data: данные для кодирования в токен
        expires_delta: время жизни токена
        secret_key: секретный ключ для подписи
        algorithm: алгоритм подписи

    Returns:
        str: JWT токен
    """
    to_encode = data.copy()
    to_encode.update({"exp": datetime.now(timezone.utc) + expires_delta})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_access_token(
    token: str,
    secret_key: str,
    algorithm: str,
) -> Optional[str]:
    """
    Декодирование JWT токена

    Args:
        token: JWT токен
        secret_key: секретный ключ для проверки подписи
        algorithm: алгоритм подписи

    Returns:
        Optional[str]: username из токена или None
    """
    try:
        payload = jwt.decode(
            token, secret_key, algorithms=[algorithm]
        )
        return payload.get("sub")
    except JWTError:
        return None
