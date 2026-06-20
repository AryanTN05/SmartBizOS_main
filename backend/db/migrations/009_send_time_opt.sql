-- Migration 009 — workspace toggle for send-time optimization.
-- When true, /runs queues new runs at the prospect's next 9-11 AM local
-- (heuristic timezone via email TLD / company domain). Off by default so
-- existing flows stay deterministic.

ALTER TABLE workspace_settings
  ADD COLUMN IF NOT EXISTS send_time_optimization BOOLEAN NOT NULL DEFAULT false;
