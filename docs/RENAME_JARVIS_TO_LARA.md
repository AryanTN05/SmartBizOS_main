# Jarvis → Lara rename — deploy guide

The "Jarvis" assistant was rebranded to "Lara" across SmartBiz OS. This doc
covers what changes on the deploy side (Render + Vercel) so you don't get a
broken production after merging the rename branch.

## Backend (Render)

### 1. Env vars to rename in the Render dashboard

Open your Render service → **Environment** tab, and update these two keys.
The values stay the same — only the key name changes.

| Old key                | New key               | Notes                                              |
|------------------------|-----------------------|----------------------------------------------------|
| `JARVIS_DATABASE_URL`  | `LARA_DATABASE_URL`   | The pgvector Postgres URL Lara writes memory to    |
| `JARVIS_VOICE_MODEL`   | `LARA_VOICE_MODEL`    | Optional Gemini Live model override                |
| `JARVIS_MODEL`         | `LARA_MODEL`          | Optional text chat model override                  |

**Order of operations:** rename the env vars **before** the new code rolls out.
If you flip them after the deploy, the boot will pick up the SQLite default
(`./smartbiz_lara.db`) instead of your Postgres URL and write a fresh empty
memory store to the container's ephemeral filesystem.

### 2. DB migration

Run [011_rename_jarvis_memory_to_lara_memory.sql](../backend/db/migrations/011_rename_jarvis_memory_to_lara_memory.sql)
against your Render Postgres **before** the new code rolls out. The new code
queries the `lara_memory` table; the old table is `jarvis_memory`.

```bash
# From the Render shell, or locally with the external DB URL:
psql "$DATABASE_URL" -f backend/db/migrations/011_rename_jarvis_memory_to_lara_memory.sql
```

The script is idempotent (`IF EXISTS` guards) so re-running is safe. If you've
already applied it, the second run is a no-op.

### 3. URL changes for backend API clients

Backend HTTP routes moved from `/jarvis/*` to `/lara-smartbiz/*`. (The new
prefix is deliberately *not* `/lara/*` to avoid colliding with the existing
`/lara/*` voice-agent legacy aliases in `routers/agents_zero_to_prod.py`.)

| Old                          | New                                  |
|------------------------------|--------------------------------------|
| `POST /jarvis/session/create`| `POST /lara-smartbiz/session/create` |
| `POST /jarvis/chat`          | `POST /lara-smartbiz/chat`           |
| `POST /jarvis/upload`        | `POST /lara-smartbiz/upload`         |
| `WS   /jarvis/voice`         | `WS   /lara-smartbiz/voice`          |

The SPA itself was updated, so this only matters if you have **external**
clients (Postman collections, integration tests, third-party scripts) hitting
the old URLs.

### 4. Lead source enum

`backend/schemas.py` still accepts `"jarvis"` as a `VALID_SOURCES` value so
existing `leads` rows pass validation. New rows the AI creates use `"lara"`.
You can run a one-off `UPDATE leads SET source = 'lara' WHERE source = 'jarvis'`
later if you want to retire the alias.

## Frontend (Vercel)

No deploy-time config to change. The SPA build picks up the new component
names automatically. The user-visible route changed:

| Old           | New          |
|---------------|--------------|
| `/jarvis`     | `/lara`      |
| `/admin/jarvis` | `/admin/lara` |

If you have any old links / bookmarks / external pages pointing at `/jarvis`,
they'll 404. Add a redirect in `vercel.json` if needed:

```json
{
  "redirects": [
    { "source": "/jarvis",        "destination": "/lara",        "permanent": true },
    { "source": "/admin/jarvis",  "destination": "/admin/lara",  "permanent": true }
  ]
}
```

## What was NOT renamed (intentional)

- **`/lara/session/create`, `/lara/chat`, `/lara/voice`** in
  `routers/agents_zero_to_prod.py` — these are the pre-existing voice-agent
  legacy aliases, unrelated to the renamed assistant. They live alongside the
  new `/lara-smartbiz/*` endpoints.
- **`"Jarvis"` in agents' identity-defense prompts** (e.g. line 189 of
  `agents_zero_to_prod.py`: `"...Bella, Jarvis, ChatGPT, Gemini, Claude..."`).
  These are deny-lists of fictional AIs each agent refuses to impersonate —
  same status as ChatGPT/Gemini/Claude in the same list.
- **The legacy SQLite file `backend/smartbiz_jarvis.db`** — gitignored. The
  new default is `backend/smartbiz_lara.db`. Old file is harmless local dev
  data; delete it manually if you want a clean start.
- **`zero → prod Design System/ui_kits/smartbiz/Jarvis.jsx`** and friends —
  reference design kit, not used by the build.

## Rollback

If something goes wrong post-deploy and you need to flip back:

1. Revert the Render env vars (`LARA_*` → `JARVIS_*`).
2. Run the reverse SQL: `ALTER TABLE lara_memory RENAME TO jarvis_memory;`
   plus the matching index renames.
3. Redeploy the previous (`main`) commit.
