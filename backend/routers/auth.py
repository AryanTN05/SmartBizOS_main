"""
routers/auth.py — Admin authentication endpoints.

POST /api/auth/login  — email + password → sets HttpOnly JWT cookie
POST /api/auth/logout — clears cookie
GET  /api/session/me  — returns current session state (admin | anon)
"""

import logging
import os
import secrets
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional
from pydantic import BaseModel, EmailStr

from db.connection import get_db
from db.entities.admin_user import AdminUser
from auth.jwt import create_access_token, decode_access_token
from config import settings
import bcrypt

logger = logging.getLogger("smartbiz.auth")
router = APIRouter(prefix="/api/auth", tags=["Auth"])
session_router = APIRouter(prefix="/api/session", tags=["Session"])

def _verify_password(plain: str, hashed: str) -> bool:
    """Direct bcrypt verify — passlib's CryptContext trips a bcrypt 4.x
    compatibility bug ('password cannot be longer than 72 bytes') even on
    short inputs because of an internal sentinel check."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False

# ─────────────────────────────────────────
# SCHEMAS (local to this router)
# ─────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ─────────────────────────────────────────
# POST /api/auth/login
# ─────────────────────────────────────────
@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Admin email + password login.
    Returns admin profile and sets an HttpOnly JWT cookie (7-day TTL).
    """
    # Look up user by email (case-insensitive)
    result = await db.execute(
        select(AdminUser).where(AdminUser.email == body.email.lower())
    )
    admin = result.scalar_one_or_none()

    # Constant-time check — always verify even if user not found to prevent timing attacks
    dummy_hash = "$2b$12$invalidhashfortimingprotection000000000000000000000"
    hash_to_check = admin.bcrypt_hash if admin else dummy_hash

    password_valid = _verify_password(body.password, hash_to_check)

    if not admin or not password_valid or admin.status != "active":
        # Generic message — never reveal whether email exists
        raise HTTPException(
            status_code=401,
            detail={"code": "bad_credentials", "message": "Invalid email or password."}
        )

    # Update last_login_at
    admin.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    # Create JWT and set HttpOnly cookie
    token = create_access_token(str(admin.id))
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        samesite=settings.cookie_samesite,
        max_age=settings.jwt_expire_days * 24 * 60 * 60,
        secure=settings.cookie_secure,
    )

    logger.info(f"Admin logged in: {admin.email}")
    return {
        "kind": "admin",
        "admin": {
            "id": str(admin.id),
            "email": admin.email,
            "name": admin.name,
            "role": admin.role,
        },
    }


# ─────────────────────────────────────────
# POST /api/auth/logout
# ─────────────────────────────────────────
@router.post("/logout", status_code=204)
async def logout(response: Response):
    """Clear the admin_session cookie.

    The deletion Set-Cookie MUST carry the same SameSite + Secure flags as
    the login cookie. FastAPI's delete_cookie() defaults to samesite=lax
    without Secure, which the browser silently refuses to apply over a
    cross-site response (Vercel → Render). Result before this fix: logout
    returned 204 but the cookie stayed alive in the browser, and the user
    stayed "logged in" until the JWT expired.
    """
    response.delete_cookie(
        key="admin_session",
        path="/",
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        httponly=True,
    )


# ─────────────────────────────────────────
# POST /api/session/init  — anonymous demo session
# ─────────────────────────────────────────
@session_router.post("/init")
async def session_init(
    response: Response,
    demo_session: Optional[str] = Cookie(default=None),
):
    """
    Mint (or refresh) an anonymous demo cookie. The frontend calls this on
    "Try the 5-min demo" so the visitor has a stable per-tab identity Lara
    can attach memory + token-budget to. No DB write — the cookie is the
    state. The token-cap + 5-minute clock are enforced by lara_smartbiz/services/
    session.py against the same UUID.
    """
    sid = demo_session or secrets.token_urlsafe(16)
    now = int(time.time())
    cap_tokens = int(os.getenv("DEMO_SESSION_TOKENS", "2000"))
    cap_seconds = int(os.getenv("DEMO_SESSION_SECONDS", "300"))

    response.set_cookie(
        key="demo_session",
        value=sid,
        httponly=True,
        samesite=settings.cookie_samesite,
        max_age=cap_seconds,
        secure=settings.cookie_secure,
    )

    return {
        "id": sid,
        "session_id": sid,
        "started_at_unix": now,
        "expires_at_unix": now + cap_seconds,
        "token_cap": cap_tokens,
        "second_cap": cap_seconds,
        "tokens_used": 0,
    }


# ─────────────────────────────────────────
# GET /api/session/me
# ─────────────────────────────────────────
@session_router.get("/me")
async def session_me(
    admin_session: Optional[str] = Cookie(default=None),
    demo_session: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Polymorphic endpoint — returns who is currently logged in.
    Returns {kind: "admin", ...}, {kind: "demo", ...}, or {kind: "anon"}.
    Never returns 401 — it's a probe endpoint.
    """
    if not admin_session:
        # Demo session takes precedence over plain anon — the visitor has
        # explicitly opted into the demo via /api/session/init.
        if demo_session:
            return {
                "kind": "demo",
                "id": demo_session,
                "session_id": demo_session,
            }
        return {"kind": "anon"}

    try:
        user_id = decode_access_token(admin_session)
    except ValueError:
        return {"kind": "anon"}

    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id, AdminUser.status == "active")
    )
    admin = result.scalar_one_or_none()

    if not admin:
        return {"kind": "anon"}

    return {
        "kind": "admin",
        "admin": {
            "id": str(admin.id),
            "email": admin.email,
            "name": admin.name,
            "role": admin.role,
        }
    }
