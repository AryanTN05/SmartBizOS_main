import React from 'react';
import { SBAvatar } from '../../../components/primitives';

// Lead list rendered inside an assistant turn — the structured result card
// for `get_leads`. Matches the UI kit exactly.
export default function LeadResultCard({ items = [] }) {
  if (!items.length) return null;
  return (
    <div style={{ border: '1px solid var(--sb-line)', background: 'var(--sb-card)' }}>
      {items.map((l, i) => (
        <div key={i} style={{
          padding: '10px 12px',
          borderTop: i > 0 ? '1px solid var(--sb-line)' : 'none',
          display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <SBAvatar name={l.name} color="var(--sb-violet)" size={28} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 12.5, fontWeight: 600, color: 'var(--sb-fg)',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              {l.name}
              {l.co && <span style={{ color: 'var(--sb-fg-5)', fontWeight: 400 }}>· {l.co}</span>}
            </div>
            {l.why && <div style={{ fontSize: 11, color: 'var(--sb-fg-4)', marginTop: 2 }}>{l.why}</div>}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <div style={{
              fontFamily: 'var(--sb-font-mono)', fontSize: 14, fontWeight: 700,
              color: (l.score ?? 0) > 80 ? 'var(--sb-hot)' : 'var(--sb-warm)',
            }}>{l.score ?? '—'}</div>
            <div style={{
              fontSize: 9, color: 'var(--sb-fg-5)',
              textTransform: 'uppercase', letterSpacing: '0.15em',
              fontFamily: 'var(--sb-font-mono)',
            }}>hot</div>
          </div>
        </div>
      ))}
    </div>
  );
}
