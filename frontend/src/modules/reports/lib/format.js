// Shared formatting + defensive-stat helpers for the reports module.
// Stats is JSONB and keys may be missing — everything here returns a
// printable string (falling back to "\u2014") so pages never crash on
// a partially populated report.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function formatUnixShort(unix) {
  if (!unix && unix !== 0) return '\u2014';
  const d = new Date(unix * 1000);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

export function formatPeriodRange(report) {
  if (!report) return '\u2014';
  return `${formatUnixShort(report.period_start_unix)} \u2014 ${formatUnixShort(report.period_end_unix - 1)}`;
}

// Rough ISO-week-like number: days-since-epoch / 7. Stable enough for
// the "Week N" eyebrow — we're not doing payroll here.
export function isoWeekNumber(unix) {
  if (!unix && unix !== 0) return '\u2014';
  // Anchor on the start of the year containing `unix`.
  const d = new Date(unix * 1000);
  const start = Date.UTC(d.getUTCFullYear(), 0, 1) / 1000;
  return Math.max(1, Math.floor((unix - start) / (7 * 24 * 3600)) + 1);
}

export function pickStat(stats, path, fallback = '\u2014') {
  if (!stats) return fallback;
  const parts = path.split('.');
  let cur = stats;
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return fallback;
    cur = cur[p];
  }
  if (cur === undefined || cur === null) return fallback;
  return cur;
}

export function fmtPercent(v) {
  if (v === null || v === undefined || v === '\u2014') return '\u2014';
  const num = typeof v === 'number' ? v : parseFloat(v);
  if (Number.isNaN(num)) return '\u2014';
  // 0.084 -> 8.4%. If someone already passed 8.4 -> treat as percent.
  const pct = num <= 1 ? num * 100 : num;
  return `${pct.toFixed(1)}%`;
}

export function fmtInt(v) {
  if (v === null || v === undefined || v === '\u2014') return '\u2014';
  const num = typeof v === 'number' ? v : parseInt(v, 10);
  if (Number.isNaN(num)) return '\u2014';
  return String(num);
}

export function fmtDelta(curr, prev) {
  if (curr == null || prev == null || prev === 0) return null;
  const d = ((curr - prev) / prev) * 100;
  const sign = d >= 0 ? '+' : '';
  return `${sign}${d.toFixed(0)}%`;
}

// Derive a headline from narrative if not provided: first sentence, trimmed.
export function deriveHeadline(report) {
  if (!report) return 'Report';
  if (report.headline) return report.headline;
  const n = (report.narrative || '').trim();
  if (!n) return 'Weekly report';
  const firstDot = n.search(/[.!?]\s/);
  const head = firstDot > 0 ? n.slice(0, firstDot + 1) : n.split('\n')[0];
  return head.length > 90 ? head.slice(0, 88) + '\u2026' : head;
}

export function narrativeExcerpt(report, max = 120) {
  const n = (report?.narrative || '').trim();
  if (!n) return '\u2014';
  if (n.length <= max) return n;
  return n.slice(0, max).trimEnd() + '\u2026';
}

export function isAuthError(err) {
  return err && (err.code === 'unauthenticated' || err.status === 401);
}
