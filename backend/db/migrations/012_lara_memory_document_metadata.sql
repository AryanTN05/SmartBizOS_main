-- Migration 012 — document metadata columns on lara_memory.
--
-- The Documents page expects size_bytes, mime_type, page_count, and an
-- extraction_status/extraction_error pair so it can show upload progress
-- and surface extraction failures. Pre-this-migration, ingest_document
-- only wrote filename + chunk_index, so the UI rendered "— · — · 0 chunks"
-- on every row.
--
-- All columns are nullable so the migration is non-destructive: existing
-- rows just keep NULLs and the API tolerates them.
--
-- To apply on Render:
--   psql "$DATABASE_URL" -f backend/db/migrations/012_lara_memory_document_metadata.sql

ALTER TABLE IF EXISTS lara_memory
  ADD COLUMN IF NOT EXISTS size_bytes        INTEGER,
  ADD COLUMN IF NOT EXISTS mime_type         VARCHAR,
  ADD COLUMN IF NOT EXISTS page_count        INTEGER,
  ADD COLUMN IF NOT EXISTS extraction_status VARCHAR,
  ADD COLUMN IF NOT EXISTS extraction_error  TEXT;
