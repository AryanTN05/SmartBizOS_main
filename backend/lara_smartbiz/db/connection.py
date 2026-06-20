"""
Lara uses a dedicated sync SQLAlchemy engine (SQLite by default) that is
independent from the backend's async Postgres engine. This keeps Lara tools
(which are sync) simple and lets the demo run without external infra.

The database URL is resolved from the unified backend settings
(`lara_database_url`), and can be overridden via the legacy `DATABASE_URL`
env var for backwards compatibility.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from lara_smartbiz.config import settings

DATABASE_URL = os.getenv("LARA_DATABASE_URL") or settings.database_url

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
