"""
Lara — AI backend package for SmartBiz OS.

Typical usage:

    from fastapi import FastAPI
    from lara_smartbiz import router as lara_router, init_db

    app = FastAPI()
    init_db()                      # create tables (idempotent)
    app.include_router(lara_router)
"""

from lara_smartbiz.routers.lara import router


def init_db() -> None:
    """Create all SQL tables defined by the Lara models (idempotent)."""
    from lara_smartbiz.db.connection import engine, Base
    from lara_smartbiz.db import models  # noqa: F401  (register models on Base)

    Base.metadata.create_all(bind=engine)


__all__ = ["router", "init_db"]
