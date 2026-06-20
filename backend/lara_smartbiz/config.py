"""
Lara configuration shim.

Lara was originally standalone with its own Settings / .env. Now that it is
wired into the SmartBiz OS backend orchestrator, we delegate to the top-level
`backend/config.py` settings so the app has a single source of truth for
credentials and environment.

This module preserves the public surface (`settings.google_api_key`,
`settings.openai_api_key`, `settings.http_proxy`) used throughout the Lara
package, so no call sites need to change.
"""

from typing import Optional

from config import settings as _main_settings


class _LaraSettings:
    @property
    def google_api_key(self) -> str:
        return _main_settings.google_api_key or ""

    @property
    def openai_api_key(self) -> str:
        return _main_settings.openai_api_key or ""

    @property
    def http_proxy(self) -> Optional[str]:
        return _main_settings.http_proxy

    @property
    def database_url(self) -> str:
        return _main_settings.lara_database_url


settings = _LaraSettings()
