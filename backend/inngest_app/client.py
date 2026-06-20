"""
Single shared Inngest client. Lives in its own module to break the import
cycle between `__init__.py` (which exposes the function list) and
`functions.py` (which decorates handlers with the client).
"""

import os

import inngest

_DEV = os.getenv("INNGEST_DEV") == "1" or not os.getenv("INNGEST_SIGNING_KEY")

client = inngest.Inngest(
    app_id="smartbiz-os",
    is_production=not _DEV,
    logger=None,
)

__all__ = ["client"]
