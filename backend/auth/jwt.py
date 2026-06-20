"""
auth/jwt.py — JWT creation and verification.

Uses python-jose with HS256. Tokens live in HttpOnly cookies — the browser
never has direct JS access to them.
"""

from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from config import settings


def create_access_token(user_id: str) -> str:
    """Create a signed JWT for the given admin user ID."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """
    Decode and verify a JWT. Returns the user_id (sub claim).
    Raises ValueError if the token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        user_id: str = payload.get("sub")
        if not user_id:
            raise ValueError("Token missing subject")
        return user_id
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")
