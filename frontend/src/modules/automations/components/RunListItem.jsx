import React from 'react';
import { timeAgo, shortId } from '../lib/format.js';

// Left-rail run row. Matches the UI kit's `RunListItem` visual.
export default function RunListItem({ run, active, onClick, leadName, leadCompany }) {
  const status = run.status || 'running';
  const statusColor = {
    running: 'var(--sb-accent)',
    paused: 'var(--sb-warm)',
    branched: 'var(--sb-warm)',
    completed: 'var(--sb-lime)',
    failed: 'var(--sb-hot)',
    cancelled: 'var(--sb-fg-5)',
  }[status] || 'var(--sb-fg-4)';

  // Step progress heuristics — prefer explicit seed fields, fall back to 0/? when
  // the backend payload doesn't carry them (the contract omits step counts from
  // the list response, so we show a flat bar rather than lie).
  const step = run._step ?? (run.status === 'completed' ? 1 : 0);
  const total = run._total ?? 1;

  const display = leadName || run._lead_display || shortId(run.lead_id);
  const company = leadCompany || run._company || null;

  return (
    <div
      onClick={onClick}
      style={{
        padding: '12px 20px',
        borderBottom: '1px solid var(--sb-line)',
        background: active ? 'var(--sb-card)' : 'transparent',
        cursor: 'pointer',
        borderLeft: `2px solid ${active ? 'var(--sb-accent)' : 'transparent'}`,
        transition: 'background 160ms',
      }}
      onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = 'var(--sb-panel)'; }}
      onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent'; }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-5)' }}>
          {shortId(run.id)}
        </span>
        <span style={{
          fontFamily: 'var(--sb-font-mono)', fontSize: 10, color: statusColor,
          textTransform: 'uppercase', letterSpacing: '0.12em', fontWeight: 700,
        }}>{status}</span>
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--sb-fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {display}{company ? <span style={{ color: 'var(--sb-fg-4)', fontWeight: 400 }}> · {company}</span> : null}
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', marginTop: 2, fontFamily: 'var(--sb-font-mono)' }}>
        {run.template_key || 'template'} · {step}/{total} · {timeAgo(run.started_at_unix)}
      </div>
      <div style={{ display: 'flex', gap: 2, marginTop: 8 }}>
        {Array.from({ length: Math.max(total, 1) }).map((_, i) => (
          <div key={i} style={{
            flex: 1, height: 2,
            background: i < step ? statusColor : 'var(--sb-line-2)',
          }} />
        ))}
      </div>
    </div>
  );
}
