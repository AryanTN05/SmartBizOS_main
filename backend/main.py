import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware


# ─────────────────────────────────────────────────────────────────────────
# Structured logging — configure root logger before any other module's
# logging.getLogger() calls fire. Level via LOG_LEVEL env (default INFO).
# Format includes module + level so per-component filtering works in any
# log aggregator. Output is stderr so stdout stays clean for app data.
# ─────────────────────────────────────────────────────────────────────────
_LOG_LEVEL = (os.getenv("LOG_LEVEL") or "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stderr,
)
# Quiet down noisy libraries unless LOG_LEVEL=DEBUG.
if _LOG_LEVEL != "DEBUG":
    for noisy in ("sqlalchemy.engine", "asyncio", "httpx", "httpcore", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ─────────────────────────────────────────────────────────────────────────
# Sentry — optional. Set SENTRY_DSN to enable error capture; otherwise the
# block is a no-op. Sentry SDK is not in requirements.txt by default — we
# import it lazily so a missing dep doesn't crash the app.
# ─────────────────────────────────────────────────────────────────────────
_SENTRY_DSN = os.getenv("SENTRY_DSN")
if _SENTRY_DSN:
    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore
        from sentry_sdk.integrations.logging import LoggingIntegration  # type: ignore
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_RATE", "0.1")),
            environment=os.getenv("ENVIRONMENT", "development"),
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
        )
        logging.getLogger("smartbiz").info("Sentry enabled")
    except Exception as e:
        logging.getLogger("smartbiz").warning(
            "SENTRY_DSN set but sentry_sdk import/init failed: %s — continuing without it", e
        )

from automations.scheduler import run_forever as run_automation_scheduler
from automations.imap_poller import run_forever as run_imap_poller
from routers.auth import router as auth_router, session_router
from routers import (
    leads,
    public,
    webhooks,
    health,
    enrichment,
    automations,
    reports,
    conversations,
    documents,
    integrations,
    mcp_gateway,
    config as config_router,
    settings as settings_router,
    stream as stream_router,
    unsubscribe as unsubscribe_router,
    agents_zero_to_prod as agents_router,
)
from lara_smartbiz import router as lara_router, init_db as init_lara_db
from config import settings
from db.connection import get_db
from auth.bootstrap import bootstrap_admin_users


_INSECURE_SECRETS = {"change-me-in-production", "dev-secret-change-me", ""}


def _enforce_production_safety() -> None:
    """Refuse to boot if obvious safety guards are missing in non-dev envs.
    Runs in lifespan so a misconfigured prod deploy fails loudly instead of
    silently shipping with a public-known JWT secret + cookie-secure=False."""
    if (settings.environment or "development").lower() in {"production", "prod"}:
        if settings.jwt_secret in _INSECURE_SECRETS:
            raise RuntimeError(
                "JWT_SECRET is unset or default. Generate one and set in env "
                "(e.g. python -c 'import secrets; print(secrets.token_hex(32))')"
            )
        if not settings.cookie_secure:
            raise RuntimeError(
                "COOKIE_SECURE must be true in production (cookies must only "
                "be sent over HTTPS)."
            )
        if "*" in settings.get_cors_origins():
            raise RuntimeError(
                "CORS_ORIGINS=* is incompatible with allow_credentials=True "
                "and is rejected by browsers. Set CORS_ORIGINS to a real "
                "origin list (e.g. 'https://app.yourdomain.com')."
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before accepting traffic."""
    _enforce_production_safety()
    # Seed admin users from ADMIN_USERS_JSON env var
    async for db in get_db():
        await bootstrap_admin_users(db)
        break
    # Create Lara SQLite tables (idempotent). pgvector memory is created lazily.
    init_lara_db()
    # Background scheduler that advances automation runs by polling the DB.
    # All run state lives in automation_runs so this is restart-safe.
    scheduler_task = asyncio.create_task(run_automation_scheduler())
    # IMAP reply-detection poller — quietly noop'd if IMAP_ENCRYPTION_KEY
    # isn't set, so dev environments without inbox creds boot fine.
    imap_task = asyncio.create_task(run_imap_poller())
    try:
        yield
    finally:
        for t in (scheduler_task, imap_task):
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(
    title="SmartBiz OS API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Compress JSON responses larger than 500B. Cuts payload by ~5x for list endpoints.
app.add_middleware(GZipMiddleware, minimum_size=500)


# ─────────────────────────────────────────────────────────────────────────
# Per-request structured log. method/path/status/duration land in stderr
# under the `smartbiz.access` logger so production log aggregators can
# filter by name. Health + static endpoints are skipped to keep the logs
# readable. The middleware is the last add_middleware() call so it's the
# outermost wrapper and sees the final status code.
# ─────────────────────────────────────────────────────────────────────────
@app.middleware("http")
async def _request_log_middleware(request, call_next):
    import time as _time
    _SKIP_PREFIXES = ("/health", "/static", "/favicon", "/api/u/")
    path = request.url.path
    skip = any(path.startswith(p) for p in _SKIP_PREFIXES)
    started = _time.monotonic()
    try:
        response = await call_next(request)
    except Exception as e:
        duration_ms = int((_time.monotonic() - started) * 1000)
        logging.getLogger("smartbiz.access").exception(
            "%s %s 500 %dms err=%s", request.method, path, duration_ms, type(e).__name__,
        )
        raise
    duration_ms = int((_time.monotonic() - started) * 1000)
    if not skip:
        logger = logging.getLogger("smartbiz.access")
        # Promote 4xx/5xx to a warning so they stand out in the stream.
        level = logging.INFO
        if response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400:
            level = logging.WARNING
        logger.log(level, "%s %s %d %dms",
                   request.method, path, response.status_code, duration_ms)
    return response

# Core SmartBiz OS routers
app.include_router(health.router)
app.include_router(auth_router)
app.include_router(session_router)
app.include_router(leads.router)
app.include_router(enrichment.router)
app.include_router(public.router)
app.include_router(webhooks.router)
app.include_router(automations.router)
app.include_router(reports.router)
app.include_router(conversations.router)
app.include_router(documents.router)
app.include_router(integrations.router)
app.include_router(mcp_gateway.router)
app.include_router(config_router.router)
app.include_router(stream_router.router)
app.include_router(settings_router.router)
app.include_router(unsubscribe_router.router)
app.include_router(agents_router.router)

# Lara assistant (endpoints: /lara-smartbiz/session/create, /lara-smartbiz/chat,
# /lara-smartbiz/upload, ws /lara-smartbiz/voice)
app.include_router(lara_router)
