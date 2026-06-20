import React from 'react';

// Generic skeleton placeholder. Renders a row/block-shaped pulsing div.
// Replaces "▸ loading…" mono text on pages where a real layout is on the
// way — eliminates the blank-flash on first paint.
//
// Variants:
//   row    — horizontal bar, configurable width via `w` prop
//   card   — full-width card-shaped block
//   list   — N stacked rows with a fading height pattern
//
// Honors --sb-line-2 / --sb-bg-2 from the theme so it inherits the
// dark/light mode (when light mode lands).

export default function SBSkeleton({ variant = 'row', w, h, count = 3, style }) {
  const bar = {
    background: 'var(--sb-card)',
    border: '1px solid var(--sb-line)',
    height: h || 16,
    width: w || '100%',
    animation: 'sb-skel-pulse 1.6s ease-in-out infinite',
  };
  if (variant === 'row') {
    return <div style={{ ...bar, ...style }} aria-hidden="true" />;
  }
  if (variant === 'card') {
    return (
      <div style={{
        background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
        height: h || 64, width: w || '100%',
        animation: 'sb-skel-pulse 1.6s ease-in-out infinite',
        ...style,
      }} aria-hidden="true" />
    );
  }
  if (variant === 'list') {
    // Decreasing-opacity rows so the user's eye is drawn to the top —
    // wherever the real content will resolve first.
    const rows = Array.from({ length: count });
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, ...style }} aria-hidden="true">
        {rows.map((_, i) => (
          <div key={i} style={{
            ...bar,
            height: 16,
            opacity: Math.max(0.25, 1 - i * 0.15),
          }} />
        ))}
      </div>
    );
  }
  return null;
}

// Inject the keyframes once. Safe to import multiple times (unique id).
if (typeof document !== 'undefined' && !document.getElementById('sb-skel-keyframes')) {
  const style = document.createElement('style');
  style.id = 'sb-skel-keyframes';
  style.textContent = `
    @keyframes sb-skel-pulse {
      0%, 100% { opacity: 0.45; }
      50%      { opacity: 0.8;  }
    }
  `;
  document.head.appendChild(style);
}
