import React, { useEffect, useState } from 'react';
import { useSession } from '../../lib/SessionContext.jsx';

// Pulls `seconds_remaining` from the current demo session and ticks locally.
// If there's no demo session it renders nothing.
export default function DemoCountdown() {
  const { session } = useSession();
  const initial =
    session?.kind === 'demo' && typeof session.seconds_remaining === 'number'
      ? session.seconds_remaining
      : null;
  const [s, setS] = useState(initial ?? 0);

  useEffect(() => {
    if (initial == null) return;
    setS(initial);
    const t = setInterval(() => setS((v) => (v > 0 ? v - 1 : 0)), 1000);
    return () => clearInterval(t);
  }, [initial]);

  if (initial == null) return null;

  const m = Math.floor(s / 60);
  const sec = String(s % 60).padStart(2, '0');
  const low = s < 60;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px',
      border: `1px solid ${low ? 'var(--sb-hot)' : 'var(--sb-line-2)'}`,
      fontFamily: 'var(--sb-font-mono)', fontSize: 11, fontWeight: 600,
      color: low ? 'var(--sb-hot)' : 'var(--sb-accent)', whiteSpace: 'nowrap', flexShrink: 0,
    }}>
      <div style={{
        width: 6, height: 6, borderRadius: '50%',
        background: low ? 'var(--sb-hot)' : 'var(--sb-accent)',
        boxShadow: `0 0 8px ${low ? 'var(--sb-hot)' : 'var(--sb-accent)'}`,
        animation: 'sb-pulse 1.5s infinite', flexShrink: 0,
      }} />
      DEMO · {m}:{sec}
    </div>
  );
}
