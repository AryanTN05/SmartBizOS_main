import React from 'react';

export default function SBKbd({ children }) {
  return (
    <kbd style={{
      fontFamily: 'var(--sb-font-mono)', fontSize: 10.5, fontWeight: 500,
      color: 'var(--sb-fg-4)', background: 'var(--sb-panel)',
      border: '1px solid var(--sb-line-2)', padding: '1px 6px',
      lineHeight: 1.5, textTransform: 'uppercase',
    }}>{children}</kbd>
  );
}
