"""
Inngest integration for SmartBiz OS — durable workflows + cron jobs.

Per the Foundation/M3/M6 specs, Inngest backs:
  - M3 nurture sequences (lead.nurture.start event → multi-step workflow)
  - M6 weekly reports cron (Monday 9am UTC → aggregate + narrate)
  - M2 scraper sweeps (every 6 hours)
  - Cloud Run warmup pings during demo hours

main.py wires these via:

    from inngest.fast_api import serve
    from inngest_app import client, functions
    serve(app, client, functions)

Local dev:
  1. brew install inngest/inngest         (or: npx inngest-cli@latest dev)
  2. INNGEST_DEV=1 uvicorn main:app
  3. inngest-cli dev                      → discovers /api/inngest automatically
"""

import inngest

from inngest_app.client import client
from inngest_app import functions as functions_module

# Pull every Function decorated in inngest_app.functions.
functions: list[inngest.Function] = [
    obj for obj in vars(functions_module).values() if isinstance(obj, inngest.Function)
]


__all__ = ["client", "functions"]
