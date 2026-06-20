"""
auth/bootstrap.py — Seed admin users from ADMIN_USERS_JSON on startup.

Called once from main.py lifespan. Additive only — never deletes existing rows.
This means if you remove a user from env, they stay in DB (safe against
accidental lockout from a misconfigured env). Disable them via status='disabled'.
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from db.entities.admin_user import AdminUser
from config import settings

logger = logging.getLogger("smartbiz.auth.bootstrap")


async def bootstrap_admin_users(db: AsyncSession) -> None:
    """
    Insert any admin users from ADMIN_USERS_JSON that don't already exist.
    Skips entries that are already in the database (matched by email).
    """
    users = settings.get_admin_users()
    if not users:
        logger.warning(
            "ADMIN_USERS_JSON is empty or unset. "
            "No admin users will be seeded. Set it in .env to create admin accounts."
        )
        return

    for entry in users:
        email = entry.get("email", "").strip().lower()
        name = entry.get("name", "Admin")
        password_hash = entry.get("password_hash", "")

        if not email or not password_hash:
            logger.warning(f"Skipping invalid admin entry (missing email or password_hash): {entry}")
            continue

        # Check if already exists
        result = await db.execute(
            select(AdminUser).where(AdminUser.email == email)
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Admin user already exists, skipping: {email}")
            continue

        new_admin = AdminUser(
            email=email,
            name=name,
            bcrypt_hash=password_hash,
            role="admin",
            status="active",
        )
        db.add(new_admin)
        logger.info(f"Seeded new admin user: {email}")

    await db.commit()
    logger.info("Admin bootstrap complete.")
