// Small helpers shared across automation pages.

export function timeAgo(unix) {
  if (!unix) return '—';
  const s = Math.max(0, Math.floor(Date.now() / 1000) - unix);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function formatElapsed(startedUnix, endedUnix) {
  if (!startedUnix) return '—';
  const endS = endedUnix ?? Math.floor(Date.now() / 1000);
  let s = Math.max(0, endS - startedUnix);
  const d = Math.floor(s / 86400); s -= d * 86400;
  const h = Math.floor(s / 3600);  s -= h * 3600;
  const m = Math.floor(s / 60);
  if (d > 0) return `${d}d ${String(h).padStart(2, '0')}h`;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  return `${m}m`;
}

export function formatDuration(seconds) {
  if (seconds == null) return '—';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

export function shortId(id) {
  if (!id) return '—';
  const s = String(id);
  if (s.length <= 10) return s;
  return `${s.slice(0, 4)}…${s.slice(-4)}`;
}

export function isTerminal(status) {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

// Map an automation event to the TimelineStep shape used in the UI kit.
// Tries to infer `kind` + `status` from `step_name` / `outcome`.
export function eventToTimelineStep(ev, index, total) {
  const name = ev.step_name || '';
  let kind = 'run';
  if (name.startsWith('wait_') || name === 'wait_completed') {
    kind = name === 'wait_completed' ? 'sleep' : (ev.channel ? 'wait_for_event' : 'sleep');
  }
  if (name === 'branch' || name === 'branch_taken' || name.startsWith('branch')) kind = 'branch';

  // Status inference.
  const outcome = ev.outcome || '';
  let status = 'done';
  if (outcome === 'failed') status = 'failed';
  else if (outcome === 'opened' || outcome === 'clicked') status = 'done';
  else if (name.startsWith('wait_') && !['wait_completed'].includes(name) && ev.payload?.detail) status = 'active';

  // Build detail + result.
  const p = ev.payload || {};
  const result = p.result || (p.provider && p.message_id ? `${p.provider} · ${p.message_id}` : null);
  const detail = p.detail || null;
  const ms = p.ms || null;
  const duration = p.duration || null;

  return { name: name || `step_${index}`, kind, status, ms, duration, result, detail, channel: ev.channel, outcome, occurred_at_unix: ev.occurred_at_unix };
}
