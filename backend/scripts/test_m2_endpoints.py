#!/usr/bin/env python3
"""End-to-end test harness for the M2 Sales Intelligence endpoints.

Hits the orchestrator (backend/main.py) over HTTP and validates:
  - Lead CRUD + kanban-move + activity timeline (routers/leads.py)
  - Enrichment trigger / read / caching  (routers/enrichment.py)
  - Rescore (sync, cache, force)         (routers/enrichment.py)
  - Score history                         (routers/enrichment.py)

Prereqs
-------
1. Start the server from `backend/`:
     uvicorn main:app --reload --port 8000
2. `.env` in `backend/` with at least DATABASE_URL.
   To exercise the AI pipeline, also set GOOGLE_API_KEY and FIRECRAWL_API_KEY
   and pass `--with-ai`.

Usage
-----
    cd backend
    python -m scripts.test_m2_endpoints               # DB-only (fast, ~3s)
    python -m scripts.test_m2_endpoints --with-ai     # Full pipeline (~60–120s)
    python -m scripts.test_m2_endpoints --base-url http://localhost:8000
"""

import argparse
import asyncio
import sys
import time
import uuid
from typing import Any

import httpx


DEFAULT_BASE_URL = "http://localhost:8000"
REQUEST_TIMEOUT = 120.0        # AI pipeline can take a while
ENRICH_POLL_TIMEOUT = 180.0    # seconds to wait for BackgroundTask to finish
ENRICH_POLL_INTERVAL = 3.0     # seconds between polls


# ── Test result tracking ────────────────────────────────────────────────────

class Results:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.rows: list[tuple[str, str | None, str]] = []  # (status, name, detail)

    def ok(self, name: str, detail: str = "") -> None:
        self.passed += 1
        self.rows.append(("PASS", name, detail))
        print(f"  \033[32m✅ PASS\033[0m  {name}" + (f"  — {detail}" if detail else ""))

    def fail(self, name: str, detail: str = "") -> None:
        self.failed += 1
        self.rows.append(("FAIL", name, detail))
        print(f"  \033[31m❌ FAIL\033[0m  {name}" + (f"  — {detail}" if detail else ""))

    def skip(self, name: str, reason: str) -> None:
        self.skipped += 1
        self.rows.append(("SKIP", name, reason))
        print(f"  \033[33m⏭  SKIP\033[0m  {name}  — {reason}")

    def assert_eq(self, name: str, got: Any, expected: Any) -> bool:
        if got == expected:
            self.ok(name, f"{got!r}")
            return True
        self.fail(name, f"expected {expected!r}, got {got!r}")
        return False

    def assert_true(self, name: str, cond: bool, detail: str = "") -> bool:
        if cond:
            self.ok(name, detail)
            return True
        self.fail(name, detail)
        return False

    def summary(self) -> bool:
        total = self.passed + self.failed + self.skipped
        print("\n" + "═" * 60)
        print(
            f"  \033[32m{self.passed} passed\033[0m  "
            f"\033[31m{self.failed} failed\033[0m  "
            f"\033[33m{self.skipped} skipped\033[0m  "
            f"/ {total} total"
        )
        print("═" * 60)
        return self.failed == 0


def section(title: str, r: Results = None) -> None:
    print(f"\n\033[1m─── {title} ───\033[0m")


# ── Test groups ─────────────────────────────────────────────────────────────

async def check_server_up(client: httpx.AsyncClient, r: Results) -> bool:
    section("Server reachability")
    try:
        resp = await client.get("/health")
    except httpx.ConnectError as exc:
        r.fail("server reachable", f"{exc}. Is uvicorn running?")
        return False
    r.assert_eq("GET /health → 200", resp.status_code, 200)
    body = resp.json()
    r.assert_eq("service name", body.get("service"), "smartbiz-os-api")
    r.assert_eq("status", body.get("status"), "ok")
    return resp.status_code == 200


async def test_create_lead(client: httpx.AsyncClient, r: Results) -> str | None:
    section("POST /api/leads — create lead")
    payload = {
        "name": "Aryan TN",
        "email": "aryansree2003@gmail.com",
        "phone": "+91 9900106080",
        "company_domain": "canvaswork.co",
        "linkedin_url": "https://www.linkedin.com/in/aryan-tn/",
        "source": "scraper_linkedin",
        "notes": "Created by M2 test script",
        "tags": ["test", "m2"],
    }
    resp = await client.post("/api/leads/", json=payload)
    if not r.assert_eq("POST /api/leads → 201", resp.status_code, 201):
        print(f"    body: {resp.text[:300]}")
        return None

    body = resp.json()
    lead_id = body.get("id")
    r.assert_true("response has lead id", bool(lead_id), f"id={lead_id}")
    r.assert_eq("name echoed", body.get("name"), payload["name"])
    r.assert_eq("company_domain echoed", body.get("company_domain"), payload["company_domain"])
    r.assert_eq("status defaults to 'new'", body.get("status"), "new")
    r.assert_eq("source preserved", body.get("source"), "scraper_linkedin")
    r.assert_eq("tags preserved", body.get("tags"), ["test", "m2"])
    return lead_id


async def test_list_leads(client: httpx.AsyncClient, r: Results) -> None:
    section("GET /api/leads — list")
    resp = await client.get("/api/leads/", params={"limit": 5})
    r.assert_eq("GET /api/leads → 200", resp.status_code, 200)
    body = resp.json()
    r.assert_true("list response is an array", isinstance(body, list), f"len={len(body) if isinstance(body, list) else 'n/a'}")

    resp2 = await client.get("/api/leads/", params={"status": "new", "limit": 5})
    r.assert_eq("status filter → 200", resp2.status_code, 200)


async def test_get_lead(client: httpx.AsyncClient, r: Results, lead_id: str) -> None:
    section("GET /api/leads/{id}")
    resp = await client.get(f"/api/leads/{lead_id}")
    r.assert_eq("GET /api/leads/{id} → 200", resp.status_code, 200)
    r.assert_eq("lead id roundtrips", resp.json().get("id"), lead_id)

    fake = str(uuid.uuid4())
    resp404 = await client.get(f"/api/leads/{fake}")
    r.assert_eq("nonexistent lead → 404", resp404.status_code, 404)


async def test_kanban_move(client: httpx.AsyncClient, r: Results, lead_id: str) -> None:
    section("POST /api/leads/{id}/kanban-move")
    resp = await client.post(
        f"/api/leads/{lead_id}/kanban-move",
        json={"stage": "Contacted"},
    )
    r.assert_eq("kanban-move → 200", resp.status_code, 200)
    body = resp.json()
    r.assert_eq("stage updated", body.get("lead", {}).get("status"), "Contacted")

    resp2 = await client.post(
        f"/api/leads/{lead_id}/kanban-move",
        json={"stage": "NotARealStage"},
    )
    r.assert_eq("invalid stage → 422", resp2.status_code, 422)


async def test_activity_timeline(client: httpx.AsyncClient, r: Results, lead_id: str) -> None:
    section("GET /api/leads/{id}/activity")
    resp = await client.get(f"/api/leads/{lead_id}/activity")
    r.assert_eq("activity → 200", resp.status_code, 200)
    body = resp.json()
    r.assert_true("items is a list", isinstance(body.get("items"), list))
    r.assert_true("total is int", isinstance(body.get("total"), int))
    r.assert_true(
        "activity contains creation event",
        any(a.get("action_type") == "lead_created" for a in body.get("items", [])),
        f"count={body.get('total')}",
    )


# ── Enrichment (DB-only checks) ─────────────────────────────────────────────

async def test_enrichment_404_before_run(
    client: httpx.AsyncClient, r: Results, lead_id: str
) -> None:
    section("GET /api/leads/{id}/enrichment (pre-run)")
    resp = await client.get(f"/api/leads/{lead_id}/enrichment")
    r.assert_eq("no enrichment yet → 404", resp.status_code, 404)


async def test_rescore_without_enrichment(
    client: httpx.AsyncClient, r: Results, lead_id: str
) -> None:
    section("POST /api/leads/{id}/rescore (no enrichment yet)")
    resp = await client.post(f"/api/leads/{lead_id}/rescore", json={"force": False})
    r.assert_eq("rescore w/o enrichment → 409", resp.status_code, 409)
    body = resp.json()
    detail = body.get("detail") if isinstance(body, dict) else None
    reason = detail.get("reason") if isinstance(detail, dict) else None
    r.assert_eq(
        "409 detail.reason == needs_enrichment_first",
        reason,
        "needs_enrichment_first",
    )


async def test_empty_score_history(
    client: httpx.AsyncClient, r: Results, lead_id: str
) -> None:
    section("GET /api/leads/{id}/score/history (empty)")
    resp = await client.get(f"/api/leads/{lead_id}/score/history")
    r.assert_eq("score history → 200", resp.status_code, 200)
    body = resp.json()
    r.assert_eq("empty items", body.get("items"), [])
    r.assert_eq("total == 0", body.get("total"), 0)


# ── AI-gated tests ──────────────────────────────────────────────────────────

async def test_trigger_enrichment(
    client: httpx.AsyncClient, r: Results, lead_id: str
) -> str | None:
    section("POST /api/leads/{id}/enrich (queue)")
    resp = await client.post(f"/api/leads/{lead_id}/enrich", json={"force": False})
    if not r.assert_eq("enrich → 202", resp.status_code, 202):
        print(f"    body: {resp.text[:300]}")
        return None
    body = resp.json()
    r.assert_eq("lead_id echoed", body.get("lead_id"), lead_id)
    r.assert_true("job_id present", bool(body.get("job_id")))
    r.assert_eq("status == queued", body.get("status"), "queued")
    return body.get("job_id")


async def poll_enrichment_complete(
    client: httpx.AsyncClient, r: Results, lead_id: str
) -> bool:
    section("Poll until enrichment completes")
    deadline = time.monotonic() + ENRICH_POLL_TIMEOUT
    last_status: str | None = None
    while time.monotonic() < deadline:
        resp = await client.get(f"/api/leads/{lead_id}/enrichment")
        if resp.status_code == 200:
            status = resp.json().get("enrichment_status")
            if status != last_status:
                print(f"    status={status}")
                last_status = status
            if status == "completed":
                r.ok("enrichment reached 'completed'")
                return True
            if status == "failed":
                r.fail("enrichment pipeline failed")
                return False
        await asyncio.sleep(ENRICH_POLL_INTERVAL)
    r.fail(
        "enrichment did not complete in time",
        f"last_status={last_status}, timeout={ENRICH_POLL_TIMEOUT}s",
    )
    return False


async def test_enrichment_read(client: httpx.AsyncClient, r: Results, lead_id: str) -> None:
    section("GET /api/leads/{id}/enrichment (post-run)")
    resp = await client.get(f"/api/leads/{lead_id}/enrichment")
    r.assert_eq("enrichment read → 200", resp.status_code, 200)
    body = resp.json()
    r.assert_eq("lead_id roundtrips", body.get("lead_id"), lead_id)
    r.assert_eq("status == completed", body.get("enrichment_status"), "completed")
    r.assert_true(
        "at least one core field populated",
        any(body.get(k) for k in (
            "company_size", "employee_count", "industry",
            "funding_stage", "tech_stack", "pain_points",
        )),
        f"industry={body.get('industry')!r} stage={body.get('funding_stage')!r}",
    )


async def test_enrichment_cache(
    client: httpx.AsyncClient, r: Results, lead_id: str
) -> None:
    section("POST /api/leads/{id}/enrich (already_fresh + force)")
    resp = await client.post(f"/api/leads/{lead_id}/enrich", json={"force": False})
    r.assert_eq("second enrich → 202", resp.status_code, 202)
    body = resp.json()
    r.assert_eq("status == already_fresh", body.get("status"), "already_fresh")
    r.assert_true(
        "existing_enrichment_age_seconds is int",
        isinstance(body.get("existing_enrichment_age_seconds"), int),
        f"age={body.get('existing_enrichment_age_seconds')}s",
    )

    resp_forced = await client.post(f"/api/leads/{lead_id}/enrich", json={"force": True})
    r.assert_eq("forced enrich → 202", resp_forced.status_code, 202)
    r.assert_eq(
        "forced status == queued",
        resp_forced.json().get("status"),
        "queued",
    )


async def test_rescore(client: httpx.AsyncClient, r: Results, lead_id: str) -> None:
    section("POST /api/leads/{id}/rescore (sync)")
    resp = await client.post(f"/api/leads/{lead_id}/rescore", json={"force": False})
    r.assert_eq("rescore → 200", resp.status_code, 200)
    body = resp.json()
    r.assert_true("was_cached is bool", isinstance(body.get("was_cached"), bool))
    score = body.get("score", {})
    r.assert_true("score.score is int", isinstance(score.get("score"), int))
    r.assert_true(
        "score within 0..100",
        isinstance(score.get("score"), int) and 0 <= score["score"] <= 100,
        f"score={score.get('score')}",
    )
    r.assert_true("score.factors present", score.get("factors") is not None)

    section("POST /api/leads/{id}/rescore (cached)")
    resp2 = await client.post(f"/api/leads/{lead_id}/rescore", json={"force": False})
    r.assert_eq("cached rescore → 200", resp2.status_code, 200)
    r.assert_eq("was_cached true", resp2.json().get("was_cached"), True)

    section("POST /api/leads/{id}/rescore (force)")
    resp3 = await client.post(f"/api/leads/{lead_id}/rescore", json={"force": True})
    r.assert_eq("forced rescore → 200", resp3.status_code, 200)
    r.assert_eq("was_cached false", resp3.json().get("was_cached"), False)


async def test_score_history_populated(
    client: httpx.AsyncClient, r: Results, lead_id: str
) -> None:
    section("GET /api/leads/{id}/score/history (populated)")
    resp = await client.get(f"/api/leads/{lead_id}/score/history")
    r.assert_eq("score history → 200", resp.status_code, 200)
    body = resp.json()
    items = body.get("items", [])
    r.assert_true(
        "at least 2 score entries (base + force)",
        len(items) >= 2,
        f"count={len(items)}",
    )
    if len(items) >= 2:
        r.assert_true(
            "newest first ordering",
            (items[0].get("scored_at") or "") >= (items[1].get("scored_at") or ""),
            f"{items[0].get('scored_at')} vs {items[1].get('scored_at')}",
        )


# ── Lara Checks ───────────────────────────────────────────────────────────

async def test_lara_session_create(client: httpx.AsyncClient, r: Results) -> str | None:
    section("POST /lara-smartbiz/session/create")
    resp = await client.post("/lara-smartbiz/session/create")
    if not r.assert_eq("lara session → 200", resp.status_code, 200):
        print(f"    body: {resp.text[:300]}")
        return None
    
    body = resp.json()
    session_id = body.get("session_id")
    r.assert_true("session_id present", bool(session_id), f"id={session_id}")
    r.assert_eq("allowed == True", body.get("allowed"), True)
    return session_id


async def test_lara_chat(client: httpx.AsyncClient, r: Results, session_id: str) -> None:
    section("POST /lara-smartbiz/chat")
    import json
    payload = {
        "session_id": session_id,
        "input": {
            "type": "text",
            "content": "Hi Lara, list my hottest leads right now."
        },
        "history": [],
        "context": {
            "current_module": "CRM"
        }
    }
    
    async with client.stream("POST", "/lara-smartbiz/chat", json=payload) as response:
        if not r.assert_eq("lara chat stream → 200", response.status_code, 200):
            content = await response.aread()
            print(f"    body: {content.decode()[:300]}")
            return
            
        chunks = 0
        done_event_seen = False
        
        async for line in response.aiter_lines():
            if not line.strip() or not line.startswith("data: "):
                continue
            
            data_str = line[6:]
            try:
                data = json.loads(data_str)
                if "token" in data:
                    chunks += 1
                elif data.get("event") == "done":
                    done_event_seen = True
            except json.JSONDecodeError:
                pass
                
        r.assert_true("received text chunks", chunks > 0, f"chunks={chunks}")
        r.assert_true("received done event", done_event_seen)


# ── Cleanup ─────────────────────────────────────────────────────────────────

async def test_delete_lead(client: httpx.AsyncClient, r: Results, lead_id: str) -> None:
    section("DELETE /api/leads/{id}")
    resp = await client.delete(f"/api/leads/{lead_id}")
    r.assert_eq("delete → 204", resp.status_code, 204)
    resp2 = await client.get(f"/api/leads/{lead_id}")
    r.assert_eq("deleted lead → 404", resp2.status_code, 404)


# ── Driver ──────────────────────────────────────────────────────────────────

async def run(base_url: str, with_ai: bool, keep_lead: bool) -> bool:
    r = Results()
    async with httpx.AsyncClient(base_url=base_url, timeout=REQUEST_TIMEOUT) as client:
        if not await check_server_up(client, r):
            r.summary()
            return False

        lead_id = await test_create_lead(client, r)
        if not lead_id:
            r.summary()
            return False

        await test_list_leads(client, r)
        await test_get_lead(client, r, lead_id)
        await test_kanban_move(client, r, lead_id)
        await test_activity_timeline(client, r, lead_id)
        await test_enrichment_404_before_run(client, r, lead_id)
        await test_rescore_without_enrichment(client, r, lead_id)
        await test_empty_score_history(client, r, lead_id)

        if with_ai:
            job = await test_trigger_enrichment(client, r, lead_id)
            if job and await poll_enrichment_complete(client, r, lead_id):
                await test_enrichment_read(client, r, lead_id)
                await test_enrichment_cache(client, r, lead_id)
                await test_rescore(client, r, lead_id)
                await test_score_history_populated(client, r, lead_id)
                
            session_id = await test_lara_session_create(client, r)
            if session_id:
                await test_lara_chat(client, r, session_id)
        else:
            r.skip("enrichment pipeline", "pass --with-ai to exercise Gemini + Firecrawl")
            r.skip("rescore pipeline",    "requires enrichment first")
            r.skip("score history (filled)", "requires enrichment first")
            r.skip("lara endpoints",    "requires AI API keys and --with-ai")

        if keep_lead:
            r.skip("DELETE cleanup", "--keep-lead set")
            print(f"\n  Lead retained for inspection: {lead_id}")
        else:
            await test_delete_lead(client, r, lead_id)

    return r.summary()


def main() -> int:
    p = argparse.ArgumentParser(description="M2 endpoint smoke-test")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Server URL (default: %(default)s)")
    p.add_argument("--with-ai", action="store_true", help="Exercise Gemini + Firecrawl pipeline")
    p.add_argument("--keep-lead", action="store_true", help="Skip DELETE so the lead is left in the DB for inspection")
    args = p.parse_args()

    print(f"\n  Base URL: {args.base_url}")
    print(f"  With AI : {args.with_ai}")
    print(f"  Keep    : {args.keep_lead}\n")

    ok = asyncio.run(run(args.base_url, args.with_ai, args.keep_lead))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
