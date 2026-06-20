import React from 'react';

// Small panel used when a list endpoint 404s or the backend is unreachable.
// Intentionally not a spinner — bootstrap brief says "show an empty-state
// card, not a loading spinner forever".
export default function EmptyState({ title = 'Module coming online', detail, children }) {
  return (
    <div style={{
      border: '1px dashed var(--sb-line-2)', padding: '24px 20px',
      background: 'var(--sb-bg-2)', color: 'var(--sb-fg-3)',
      fontFamily: 'var(--sb-font-mono)', fontSize: 12, lineHeight: 1.6,
    }}>
      <div style={{ color: 'var(--sb-accent)', marginBottom: 6, fontWeight: 600 }}>
        ▸ {title}
      </div>
      {detail || 'Seed data not loaded yet.'}
      {children}
    </div>
  );
}
