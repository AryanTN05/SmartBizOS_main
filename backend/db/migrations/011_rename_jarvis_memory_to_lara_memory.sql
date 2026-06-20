-- Migration 011 — rename jarvis_memory → lara_memory.
--
-- Background: the Jarvis assistant was rebranded to Lara. The pgvector-backed
-- semantic memory table is renamed to keep storage names aligned with the
-- new brand. Indexes are renamed alongside the table.
--
-- Safe to re-run: each statement is guarded with `IF EXISTS` so partial /
-- already-applied state doesn't error out.
--
-- To apply on Render:
--   psql "$DATABASE_URL" -f backend/db/migrations/011_rename_jarvis_memory_to_lara_memory.sql

ALTER TABLE IF EXISTS jarvis_memory RENAME TO lara_memory;

-- Rename pgvector / btree indexes that SQLAlchemy auto-created under the old
-- table name. These match the column shape declared in
-- backend/db/entities/lara_memory.py — adjust if your DB has additional
-- custom indexes.
ALTER INDEX IF EXISTS jarvis_memory_pkey RENAME TO lara_memory_pkey;
ALTER INDEX IF EXISTS ix_jarvis_memory_session_id RENAME TO ix_lara_memory_session_id;
