"""Enrichment engine — LLM-powered lead enrichment and scoring.

This package is consumed by `backend/routers/enrichment.py`. It does NOT own any
FastAPI app, DB session, or settings object — all of that comes from the
orchestrator. On import, we propagate the LLM API keys from orchestrator
settings into `os.environ` so that downstream SDKs (litellm, firecrawl)
pick them up automatically.
"""

import os

from config import settings

if settings.google_api_key and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = settings.google_api_key

if settings.firecrawl_api_key and not os.environ.get("FIRECRAWL_API_KEY"):
    os.environ["FIRECRAWL_API_KEY"] = settings.firecrawl_api_key
