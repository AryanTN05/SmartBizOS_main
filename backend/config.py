from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Union, Optional
import json


class Settings(BaseSettings):
    # ── Database ────────────────────────────────────────────
    database_url: str

    # ── CORS ────────────────────────────────────────────────
    cors_origins: Union[str, List[str]] = ["*"]

    # ── Tenant ──────────────────────────────────────────────
    default_tenant_id: str = "00000000-0000-0000-0000-000000000001"

    # ── Auth ────────────────────────────────────────────────
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    # MUST be overridden in production (lifespan startup will refuse to boot
    # if it's still the default — see main.py).
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7
    # Cookie hardening. Default False so local dev (http://localhost) works
    # without HTTPS; flip to True in prod via env (Render auto-provides
    # HTTPS at the edge). Unset env in prod = boot refusal.
    cookie_secure: bool = False
    # Lax is fine for our cookie-auth API since all state-changing endpoints
    # are JSON POST/PATCH (not form submissions). Strict is the long-term goal.
    cookie_samesite: str = "lax"
    # Set to a real env name ("production", "staging") to enable strict
    # startup checks for jwt_secret + cors_origins + cookie_secure.
    environment: str = "development"

    # JSON array of {email, name, password_hash} seeded into admin_users on startup
    # Example: [{"email":"admin@example.com","name":"Admin","password_hash":"$2b$12$..."}]
    # Generate hash with: python -c "from passlib.context import CryptContext; c=CryptContext(schemes=['bcrypt']); print(c.hash('yourpassword'))"
    admin_users_json: str = "[]"
    # Enrichment engine — LLM + scraper keys. Optional so the app boots without them;
    # the enrichment endpoints will fail at call time with a clear error if missing.
    google_api_key: Optional[str] = None
    firecrawl_api_key: Optional[str] = None
    gemini_model: str = "gemini-3-flash-preview"

    # Lara assistant — embeddings + optional outbound proxy. Optional so the app boots
    # without them; Lara endpoints will fail at call time if required keys are missing.
    openai_api_key: Optional[str] = None
    http_proxy: Optional[str] = None

    # Lara local storage. Defaults to SQLite alongside the backend
    # process so the demo runs with zero external infra.
    lara_database_url: str = "sqlite:///./smartbiz_lara.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_cors_origins(self) -> List[str]:
        if isinstance(self.cors_origins, str):
            if self.cors_origins.startswith("["):
                try:
                    return json.loads(self.cors_origins)
                except Exception:
                    pass
            return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return self.cors_origins

    def get_admin_users(self) -> List[dict]:
        """Parse ADMIN_USERS_JSON into a list of dicts."""
        try:
            return json.loads(self.admin_users_json)
        except Exception:
            return []


settings = Settings()
