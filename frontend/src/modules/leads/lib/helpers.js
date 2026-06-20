// Small utilities shared across the module.

export function scoreTone(value) {
  if (value == null) return 'var(--sb-fg-4)';
  if (value >= 80) return 'var(--sb-hot)';
  if (value >= 60) return 'var(--sb-warm)';
  return 'var(--sb-fg-4)';
}

export function tagTone(tag) {
  if (tag === 'hot') return 'hot';
  if (tag === 'warm') return 'warm';
  if (tag === 'fintech') return 'cool';
  if (tag === 'won') return 'lime';
  return 'neutral';
}

export function sourceIcon(source) {
  if (!source) return 'building';
  if (source.includes('linkedin')) return 'linkedin';
  if (source === 'lara') return 'lara';
  if (source === 'hubspot' || source === 'zoho' || source === 'sheets' || source === 'tally') return 'at';
  if (source.startsWith('scraper_')) return 'leads';
  return 'building';
}

export function activityIcon(kind) {
  switch (kind) {
    case 'email': return 'mail';
    case 'note': return 'docs';
    case 'status_change': return 'flow';
    case 'enrichment': return 'spark';
    case 'automation_event': return 'flow';
    case 'score_changed': return 'trend';
    case 'mcp_sync': return 'leads';
    case 'reply_received': return 'flame';
    default: return 'dot';
  }
}

export function activityColor(kind) {
  switch (kind) {
    case 'email': return 'var(--sb-accent)';
    case 'enrichment': return 'var(--sb-warm)';
    case 'automation_event': return 'var(--sb-violet)';
    case 'score_changed': return 'var(--sb-lime)';
    case 'status_change': return 'var(--sb-cool)';
    case 'reply_received': return 'var(--sb-hot)';
    default: return 'var(--sb-fg-4)';
  }
}

// Relative time in a compact form — "2h ago", "3d ago", "just now".
export function relTime(unix) {
  if (!unix) return '—';
  const now = Math.floor(Date.now() / 1000);
  const d = now - unix;
  if (d < 60) return 'just now';
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  if (d < 86400 * 30) return `${Math.floor(d / 86400)}d ago`;
  return new Date(unix * 1000).toLocaleDateString();
}

// "2:14 PM" style — used for event timestamps when we have them fresh.
export function shortTime(unix) {
  if (!unix) return '';
  const d = new Date(unix * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Visual mapping for reply intent (LLM-classified). The chip on lead cards
// + drawers reads from this so the SDR knows where to spend time first.
export function intentMeta(intent) {
  switch (intent) {
    case 'positive':     return { tone: 'lime',    label: 'positive',     icon: 'check' };
    case 'negative':     return { tone: 'hot',     label: 'negative',     icon: 'close' };
    case 'wrong_person': return { tone: 'warm',    label: 'wrong person', icon: 'spark' };
    case 'unsubscribe':  return { tone: 'hot',     label: 'unsubscribe',  icon: 'close' };
    case 'auto_reply':   return { tone: 'muted',   label: 'auto-reply',   icon: 'clock' };
    case 'neutral':      return { tone: 'neutral', label: 'neutral',      icon: 'dot' };
    default:             return null;
  }
}

// Visual for trigger badges (job/funding/etc).
export function triggerMeta(trigger) {
  switch (trigger) {
    case 'hiring':            return { tone: 'cool', label: 'hiring',     icon: 'leads' };
    case 'funding':           return { tone: 'lime', label: 'funded',     icon: 'spark' };
    case 'tech_stack_change': return { tone: 'warm', label: 'stack-shift', icon: 'flow' };
    case 'launch':            return { tone: 'accent', label: 'launching', icon: 'flame' };
    default:                  return { tone: 'neutral', label: trigger, icon: 'dot' };
  }
}

// Friendly category label.
export function scoreCategory(value) {
  if (value == null) return 'unscored';
  if (value >= 80) return 'hot';
  if (value >= 60) return 'warm';
  if (value >= 40) return 'cold';
  return 'unqualified';
}
