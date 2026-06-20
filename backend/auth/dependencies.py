"""
auth/dependencies.py — FastAPI dependency that enforces admin authentication.

Usage in any router:
    from auth.dependencies import require_admin

    @router.get("/something")
    async def my_route(admin: AdminUser = Depends(require_admin), ...):
        ...
"""

import logging
from fastapi import Depends, HTTPException, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional

from db.connection import get_db
from db.entities.admin_user import AdminUser
from auth.jwt import decode_access_token

logger = logging.getLogger("smartbiz.auth")


async def require_admin(
    admin_session: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """
    FastAPI dependency that:
    1. Reads the `admin_session` HttpOnly cookie
    2. Decodes and verifies the JWT
    3. Looks up the admin user in the DB
    4. Returns the AdminUser if valid, raises 401 otherwise

    Plug into any admin route with: Depends(require_admin)
    """
    if not admin_session:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "No admin session found. Please log in."}
        )

    try:
        user_id = decode_access_token(admin_session)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Session expired or invalid. Please log in again."}
        )

    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id, AdminUser.status == "active")
    )
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Admin account not found or disabled."}
        )

    return admin
