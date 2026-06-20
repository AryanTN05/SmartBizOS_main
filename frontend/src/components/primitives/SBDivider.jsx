import React from 'react';

export default function SBDivider({ label, style }) {
  if (!label) return <div style={{ height: 1, background: 'var(--sb-line)', ...style }} />;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, ...style }}>
      <div style={{ flex: 1, height: 1, background: 'var(--sb-line)' }} />
      <span className="sb-label">{label}</span>
      <div style={{ flex: 1, height: 1, background: 'var(--sb-line)' }} />
    </div>
  );
}
