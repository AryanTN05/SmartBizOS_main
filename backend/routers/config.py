"""
routers/config.py — public app config the frontend boots with.

GET /api/config — returns version, environment, feature flags, demo limits.
The frontend reads this on every page load via SessionContext to decide
which features to render (voice, Hindi voice, M7 fintech, live scrapers).

Anonymous-readable. No PII.
"""

import os

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["Config"])


def _truthy(env_value: str | None, default: bool = False) -> bool:
    if env_value is None:
        return default
    return env_value.strip().lower() in {"1", "true", "yes", "on"}


@router.get("/config")
async def get_config() -> dict:
    """Boot-time config snapshot. Shape matches the frontend's FALLBACK_CONFIG."""
    return {
        "version": os.getenv("APP_VERSION", "0.1.0-dev"),
        "environment": os.getenv("APP_ENVIRONMENT", "dev"),
        "features": {
            # Voice/Hindi gated on having TTS+STT keys configured AND the flag.
            "voice_enabled": _truthy(os.getenv("FEATURE_VOICE_ENABLED")),
            "hindi_voice_enabled": _truthy(os.getenv("FEATURE_HINDI_VOICE_ENABLED")),
            # M7 fintech is the optional module per the project plan.
            "m7_fintech_enabled": _truthy(os.getenv("FEATURE_M7_FINTECH_ENABLED")),
            # Scrapers behind a flag because they hit external services.
            "scraper_live_enabled": _truthy(os.getenv("FEATURE_SCRAPER_LIVE_ENABLED")),
        },
        "demo_limits": {
            "session_seconds": int(os.getenv("DEMO_SESSION_SECONDS", "300")),
            "session_tokens": int(os.getenv("DEMO_SESSION_TOKENS", "2000")),
            "ip_rate_limit_per_hour": int(os.getenv("DEMO_IP_RATE_LIMIT_PER_HOUR", "1")),
        },
    }
