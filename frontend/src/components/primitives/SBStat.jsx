import React from 'react';
import SBIcon from './SBIcon.jsx';

export default function SBStat({ label, value, delta, trend = 'up', mono }) {
  return (
    <div style={{ padding: '18px 20px', background: 'var(--sb-card)', border: '1px solid var(--sb-line)' }}>
      <div className="sb-label">{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 10 }}>
        <div style={{
          fontSize: 30, fontWeight: 500, letterSpacing: '-0.02em', color: 'var(--sb-fg)',
          fontFamily: mono ? 'var(--sb-font-mono)' : 'var(--sb-font)', lineHeight: 1, whiteSpace: 'nowrap',
        }}>{value}</div>
        {delta && (
          <div style={{
            fontSize: 11, fontWeight: 700, fontFamily: 'var(--sb-font-mono)',
            color: trend === 'up' ? 'var(--sb-accent)' : trend === 'hot' ? 'var(--sb-hot)' : 'var(--sb-warm)',
            display: 'flex', alignItems: 'center', gap: 3, whiteSpace: 'nowrap',
          }}>
            <SBIcon name={trend === 'down' ? 'arrowDown' : 'arrowUp'} size={11} stroke={2} />
            {delta}
          </div>
        )}
      </div>
    </div>
  );
}
