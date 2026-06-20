"""
Test fixtures for SmartBiz OS.

Configures env vars before `main` is imported so the FastAPI app boots
without a real Postgres or any LLM keys, then exposes a sync TestClient
shared across the suite.
"""

import os
import sys
from pathlib import Path

import pytest

# Backend dir on sys.path so `import main` resolves before fixtures run.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://localhost/smartbiz_test")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")
os.environ.setdefault("ADMIN_USERS_JSON", "[]")
os.environ.setdefault("CORS_ORIGINS", "*")
os.environ.setdefault("INNGEST_DEV", "1")


@pytest.fixture(scope="session")
def app():
    """Import the FastAPI app exactly once per test session."""
    import main  # noqa: WPS433 — late import on purpose so env vars apply
    return main.app


@pytest.fixture()
def client(app):
    """Sync TestClient for all routes — works for both sync and async handlers."""
    from fastapi.testclient import TestClient
    return TestClient(app)
