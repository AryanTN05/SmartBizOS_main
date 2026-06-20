import React from 'react';
import { SBIcon } from '../../../components/primitives';

// The three-bouncing-dots "calling tools…" indicator. Lifted from the UI kit.
export default function ThinkingIndicator({ label = 'calling tools…' }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      color: 'var(--sb-fg-4)', fontSize: 12, fontFamily: 'var(--sb-font-mono)',
      marginBottom: 18,
    }}>
      <div style={{
        width: 24, height: 24, background: 'var(--sb-accent-bg)',
        color: 'var(--sb-accent)', display: 'flex',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <SBIcon name="lara" size={13} stroke={1.5} />
      </div>
      <div style={{ display: 'flex', gap: 4 }}>
        {[0, 1, 2].map((i) => (
          <div key={i} style={{
            width: 5, height: 5, background: 'var(--sb-accent)', borderRadius: '50%',
            animation: `sb-bounce 1.4s infinite ${i * 0.15}s`,
          }} />
        ))}
      </div>
      <span>{label}</span>
    </div>
  );
}
