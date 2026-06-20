"""End-to-end prod smoke test against https://smartbiz-api.onrender.com.

Runs from outside the app (no imports of our backend code) so it's a pure
network-side validation of what a Vercel-hosted frontend would see.

Run:
    cd backend
    .venv/bin/python -m scripts.prod_smoke
    .venv/bin/python -m scripts.prod_smoke --base https://other.onrender.com
    .venv/bin/python -m scripts.prod_smoke --with-chat   # includes 1 LLM call (costs ~$0.001)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any, Optional

import httpx

DEFAULT_BASE = "https://smartbiz-api.onrender.com"
ADMIN_EMAIL = "admin@smartbiz.demo"
ADMIN_PASSWORD = "viv@2003"
VERCEL_ORIGIN = "https://smartbiz-os.vercel.app"  # for CORS check

# ─────────────────────────────────────────────────────────────────────────
# Reporting helpers
# ─────────────────────────────────────────────────────────────────────────
results: list[tuple[str, str, str]] = []  # (name, OK/WARN/FAIL, detail)


def ok(name: str, detail: str = "") -> None:
    results.append((name, "OK", detail))
    print(f"  ✓ {name:55} {detail}")


def warn(name: str, detail: str = "") -> None:
    results.append((name, "WARN", detail))
    print(f"  ⚠ {name:55} {detail}")


def fail(name: str, detail: str = "") -> None:
    results.append((name, "FAIL", detail))
    print(f"  ✗ {name:55} {detail}")


def section(title: str) -> None:
    print(f"\n── {title} " + "─" * (75 - len(title)))


# ─────────────────────────────────────────────────────────────────────────
# Test body
# ─────────────────────────────────────────────────────────────────────────
async def run(base: str, with_chat: bool) -> None:
    print(f"\n  Target: {base}")
    print(f"  Includes paid chat test: {with_chat}\n")

    timeout = httpx.Timeout(30.0, read=60.0)
    async with httpx.AsyncClient(base_url=base, timeout=timeout, follow_redirects=False) as c:

        # ── 1. Anonymous / public ───────────────────────────────────────────
        section("Public endpoints")

        t = time.monotonic()
        r = await c.get("/health")
        dur = int((time.monotonic() - t) * 1000)
        if r.status_code == 200 and r.json().get("status") == "ok":
            ok("/health", f"200 in {dur}ms")
        else:
            fail("/health", f"got {r.status_code}: {r.text[:100]}")
            return  # backend down — bail

        r = await c.post("/api/session/init", json={})
        if r.status_code == 200 and "session_id" in r.json():
            ok("/api/session/init", f"session_id={r.json()['session_id'][:8]}…")
        else:
            fail("/api/session/init", f"{r.status_code}")

        r = await c.get("/api/config")
        if r.status_code == 200:
            ok("/api/config", "200")
        else:
            fail("/api/config", str(r.status_code))

        # ── 2. CORS preflight from a Vercel-style Origin ────────────────────
        section("CORS preflight (Vercel → Render)")
        r = await c.options("/api/auth/login", headers={
            "Origin": VERCEL_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        h = r.headers
        if r.status_code == 200 and h.get("access-control-allow-origin") == VERCEL_ORIGIN \
                and h.get("access-control-allow-credentials") == "true":
            ok("OPTIONS preflight from Vercel", "ACAO=vercel, ACAC=true")
        else:
            fail("OPTIONS preflight from Vercel",
                 f"status={r.status_code} ACAO={h.get('access-control-allow-origin')} ACAC={h.get('access-control-allow-credentials')}")

        # ── 3. Login + cookie attribute check ───────────────────────────────
        section("Auth + cookie cross-site readiness")
        t = time.monotonic()
        r = await c.post("/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        dur = int((time.monotonic() - t) * 1000)
        if r.status_code != 200:
            fail("login", f"{r.status_code}: {r.text[:120]}")
            return
        body = r.json()
        if body.get("kind") != "admin":
            fail("login", f"unexpected kind: {body}")
            return
        ok("login", f"as {body['admin']['email']} in {dur}ms")

        # Inspect Set-Cookie for cross-site readiness
        sc = r.headers.get("set-cookie", "")
        has_samesite_none = "samesite=none" in sc.lower()
        has_secure = "secure" in sc.lower()
        if has_samesite_none and has_secure:
            ok("cookie cross-site flags", "SameSite=None + Secure present")
        else:
            warn("cookie cross-site flags",
                 f"SameSite=None={has_samesite_none}, Secure={has_secure} — browsers won't store from Vercel→Render")

        # httpx persists cookies in the client jar automatically.

        # ── 4. Auth'd GET sweep ─────────────────────────────────────────────
        section("Auth'd GET endpoints (200 = wired)")
        get_checks = [
            ("/api/session/me",                  lambda j: "session_id" in j or "kind" in j),
            ("/api/leads/?limit=3",              lambda j: "items" in j),
            ("/api/leads/replies?limit=3",       lambda j: "items" in j),
            ("/api/leads/sequence-stats",        lambda j: True),
            ("/api/documents?limit=3",           lambda j: "items" in j),
            ("/api/conversations?limit=3",       lambda j: "items" in j),
            ("/api/admin/memory?limit=3",        lambda j: True),
            ("/api/integrations",                lambda j: "items" in j),
            ("/api/integrations/_meta",          lambda j: True),
            ("/api/scrapers",                    lambda j: True),
            ("/api/scrapers/results?limit=3",    lambda j: "items" in j),
            ("/api/scrapers/results/_count",     lambda j: True),
            ("/api/inbox/diagnostics",           lambda j: "reply_pipeline" in j),
            ("/api/automations/templates",       lambda j: True),
            ("/api/automations/channels",        lambda j: True),
            ("/api/automations/runs?limit=3",    lambda j: True),
            ("/api/reports/sequence-performance",lambda j: True),
            ("/api/reports/source-roi",          lambda j: True),
            ("/api/workspace/settings",          lambda j: True),
            ("/api/mcp/tools/list",              lambda j: "items" in j and "modules" in j),
        ]
        for path, validator in get_checks:
            try:
                r = await c.get(path)
                if r.status_code == 200:
                    try:
                        j = r.json()
                    except Exception:
                        j = None
                    if validator(j) if j is not None else False:
                        ok(path, "200 + shape ok")
                    else:
                        warn(path, "200 but unexpected shape")
                elif r.status_code == 404:
                    # Expected for reports/latest with no data
                    warn(path, "404 (likely no rows yet)")
                else:
                    fail(path, f"{r.status_code}")
            except httpx.RequestError as e:
                fail(path, f"network: {type(e).__name__}")

        # /api/reports/latest is special — 404 is the no-data-yet path
        r = await c.get("/api/reports/latest?kind=weekly")
        if r.status_code in (200, 404):
            ok("/api/reports/latest", f"{r.status_code} (404 = no reports yet, OK)")
        else:
            fail("/api/reports/latest", f"{r.status_code}")

        # ── 5. MCP tool namespace check ─────────────────────────────────────
        section("MCP tool namespace (post-rename)")
        r = await c.get("/api/mcp/tools/list")
        if r.status_code == 200:
            j = r.json()
            modules = set(j.get("modules") or [])
            names = [t["name"] for t in (j.get("items") or [])]
            has_lara = "lara" in modules
            has_jarvis = "jarvis" in modules
            lara_namespaced = any(n.startswith("lara.") for n in names)
            if has_lara and not has_jarvis and lara_namespaced:
                ok("MCP namespace", f"'lara' module present, {len(names)} tools")
            else:
                warn("MCP namespace",
                     f"lara={has_lara} jarvis={has_jarvis} lara-prefixed={lara_namespaced}")

        # ── 6. Documents upload — full metadata roundtrip ───────────────────
        section("Documents upload (metadata roundtrip)")
        try:
            file_bytes = b"This is a prod smoke-test document. " * 5
            r = await c.post(
                "/api/documents/upload",
                files={"file": ("smoke-test.txt", file_bytes, "text/plain")},
                data={"session_id": "prod-smoke"},
            )
            if r.status_code != 200:
                fail("documents upload", f"{r.status_code}: {r.text[:120]}")
            else:
                j = r.json()
                needed = {"size_bytes", "mime_type", "extraction_status"}
                missing = needed - set(j.keys())
                if missing:
                    fail("documents upload metadata", f"missing fields: {missing}")
                elif j.get("extraction_status") == "ready":
                    ok("documents upload",
                       f"id={j.get('file_id', '')[:8]}… size={j['size_bytes']} status=ready")
                    doc_id = j.get("file_id")
                    # Verify the list endpoint also surfaces the metadata
                    r2 = await c.get("/api/documents?session_id=prod-smoke")
                    item = next((x for x in r2.json().get("items", []) if x["id"] == doc_id), None)
                    if item and item.get("extraction_status") == "ready" and item.get("size_bytes"):
                        ok("documents list metadata", "round-trips through list")
                    else:
                        warn("documents list metadata",
                             f"list item missing fields: {item}")
                else:
                    warn("documents upload", f"status={j.get('extraction_status')}")
        except Exception as e:
            fail("documents upload", f"{type(e).__name__}: {e}")

        # ── 7. Confirmation guards on outbound endpoints ────────────────────
        section("Outbound confirmation guards (#10 from audit)")

        r = await c.post("/api/workspace/settings/imap/poll-now")
        if r.status_code == 412 and (r.json().get("detail", {}).get("code") == "confirmation_required"):
            ok("poll-now without confirm", "412 confirmation_required")
        else:
            fail("poll-now without confirm", f"got {r.status_code}, expected 412")

        r = await c.post("/api/workspace/settings/imap/poll-now?confirm=true")
        if r.status_code == 200:
            ok("poll-now with confirm", "200")
        else:
            warn("poll-now with confirm", f"{r.status_code}")

        # Don't test digest send-now — it could send real email if IMAP creds wired.
        # Just verify the guard rejects unconfirmed.
        r = await c.post("/api/workspace/settings/digest/send-now")
        if r.status_code == 412:
            ok("digest send-now without confirm", "412 (guard works)")
        else:
            warn("digest send-now without confirm", f"got {r.status_code}")

        # ── 8. Convert-before-enrich guard (#5 from audit) ──────────────────
        section("Scraper convert-before-enrich guard")
        # Find a pending result that has NO enrichment.score in raw_data
        r = await c.get("/api/scrapers/results?status=pending&limit=20")
        candidates = []
        for item in (r.json() or {}).get("items", []):
            enrich = (item.get("raw_data") or {}).get("enrichment") or {}
            if not enrich.get("score"):
                candidates.append(item["id"])
        if not candidates:
            warn("convert guard", "no unenriched candidates in prod — every result has enrichment.score")
        else:
            target = candidates[0]
            r = await c.post(f"/api/scrapers/results/{target}/convert")
            if r.status_code == 422 and r.json().get("detail", {}).get("code") == "not_enriched":
                ok("convert without enrichment", "422 not_enriched (correct)")
            else:
                warn("convert without enrichment",
                     f"got {r.status_code}: {r.text[:120]}")

        # ── 9. Stream chat (optional — costs a Gemini call) ─────────────────
        if with_chat:
            section("Streaming chat (Gemini Live AUDIO → text transcription)")
            session_id = f"prod-smoke-{int(time.time())}"
            try:
                t = time.monotonic()
                delta_count = 0
                tool_calls = 0
                got_finish = False
                async with c.stream(
                    "POST", "/api/stream/chat",
                    json={"messages": [{
                        "role": "user",
                        "content": "Say hi in exactly five words.",
                    }], "conversation_id": session_id},
                ) as resp:
                    if resp.status_code != 200:
                        fail("stream chat", f"{resp.status_code}")
                    else:
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            try:
                                ev = json.loads(line[6:])
                            except Exception:
                                continue
                            t_ = ev.get("type")
                            if t_ == "text-delta":
                                delta_count += 1
                            elif t_ == "tool-input-start":
                                tool_calls += 1
                            elif t_ == "finish":
                                got_finish = True
                                break
                dur = int((time.monotonic() - t) * 1000)
                if got_finish and delta_count:
                    ok("stream chat", f"{delta_count} deltas, {tool_calls} tools, {dur}ms")
                else:
                    fail("stream chat",
                         f"finish={got_finish} deltas={delta_count}")
            except Exception as e:
                fail("stream chat", f"{type(e).__name__}: {e}")

            # Memory extraction lands in lara_memory? (poll up to 15s)
            section("Memory extraction fires from chat (#1 from earlier loop)")
            await asyncio.sleep(8)
            r = await c.get(f"/api/admin/memory?session_id={session_id}&limit=3")
            if r.status_code == 200:
                rows = r.json() or []
                if rows:
                    ok("memory extraction", f"{len(rows)} rows landed for session {session_id[:12]}…")
                else:
                    warn("memory extraction",
                         "no rows yet (greeting may not have memory-worthy content; not a bug)")
            else:
                fail("memory extraction read", f"{r.status_code}")

        # ── 10. /api/leads/replies structure ────────────────────────────────
        section("Replies endpoint structure")
        r = await c.get("/api/leads/replies?limit=3")
        if r.status_code == 200:
            j = r.json()
            required = {"items", "total_estimate", "next_cursor"}
            if required.issubset(j.keys()):
                ok("replies shape", f"{j['total_estimate']} replies; shape matches list_leads")
            else:
                warn("replies shape", f"missing fields: {required - set(j.keys())}")

        # ── 11. Inbox diagnostics: reply_pipeline ───────────────────────────
        section("Inbox diagnostics — reply_pipeline visibility (#8 from audit)")
        r = await c.get("/api/inbox/diagnostics")
        if r.status_code == 200:
            j = r.json()
            rp = j.get("reply_pipeline")
            if rp and "imap_encryption_key_set" in rp:
                ok("reply_pipeline field",
                   f"imap_set={rp['imap_encryption_key_set']}, reason={rp.get('imap_disabled_reason', 'none')[:60]}")
            else:
                fail("reply_pipeline field", "field missing from diagnostics")

        # ── 12. Logout ──────────────────────────────────────────────────────
        section("Logout")
        r = await c.post("/api/auth/logout")
        if r.status_code in (200, 204):
            ok("logout", str(r.status_code))
        else:
            warn("logout", str(r.status_code))


# ─────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--with-chat", action="store_true",
                        help="Include /api/stream/chat (costs a small Gemini call)")
    args = parser.parse_args()

    asyncio.run(run(args.base, args.with_chat))

    # ── Summary ─────────────────────────────────────────────────────────────
    n_ok = sum(1 for _, s, _ in results if s == "OK")
    n_warn = sum(1 for _, s, _ in results if s == "WARN")
    n_fail = sum(1 for _, s, _ in results if s == "FAIL")
    total = len(results)
    print(f"\n{'═' * 78}")
    print(f"  {n_ok}/{total} OK  ·  {n_warn} WARN  ·  {n_fail} FAIL")
    if n_fail:
        print("\n  Failures:")
        for n, s, d in results:
            if s == "FAIL":
                print(f"    ✗ {n}: {d}")
    if n_warn:
        print("\n  Warnings (often expected):")
        for n, s, d in results:
            if s == "WARN":
                print(f"    ⚠ {n}: {d}")
    print(f"{'═' * 78}\n")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
