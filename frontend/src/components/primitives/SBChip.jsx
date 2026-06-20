import React from 'react';
import SBIcon from './SBIcon.jsx';

export default function SBChip({ children, tone = 'neutral', solid, icon }) {
  const tones = {
    neutral: { bg: 'var(--sb-card)', fg: 'var(--sb-fg-3)' },
    accent:  { bg: 'var(--sb-accent-bg)', fg: 'var(--sb-accent)' },
    hot:     { bg: 'rgba(255,90,106,0.1)', fg: 'var(--sb-hot)' },
    warm:    { bg: 'rgba(255,181,71,0.1)', fg: 'var(--sb-warm)' },
    cool:    { bg: 'rgba(125,211,252,0.1)', fg: 'var(--sb-cool)' },
    violet:  { bg: 'rgba(183,148,255,0.1)', fg: 'var(--sb-violet)' },
    lime:    { bg: 'rgba(163,255,90,0.1)', fg: 'var(--sb-lime)' },
    muted:   { bg: 'transparent', fg: 'var(--sb-fg-4)', border: '1px solid var(--sb-line-2)' },
  };
  const t = tones[tone];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      fontSize: 10.5, fontWeight: 600, padding: '2px 8px',
      fontFamily: 'var(--sb-font-mono)', letterSpacing: '0.06em', textTransform: 'uppercase',
      background: solid ? t.fg : t.bg, color: solid ? '#000' : t.fg,
      border: t.border || 'none', lineHeight: 1.7, whiteSpace: 'nowrap',
    }}>
      {icon && <SBIcon name={icon} size={10} stroke={1.8} />}
      {children}
    </span>
  );
}
