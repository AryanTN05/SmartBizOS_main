import React from 'react';
import { SBCard } from '../components/primitives';

// Placeholder used for every admin/* module route until the module agent
// replaces it with real content. Keeps the shell navigable while the
// foundation ships.
export default function ModuleStub({ module: mod = 'Module' }) {
  return (
    <div style={{ padding: '48px 32px', display: 'flex', justifyContent: 'center' }}>
      <SBCard bracket style={{ padding: 36, maxWidth: 520, width: '100%' }}>
        <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 10 }}>{mod}</div>
        <h1 style={{ margin: 0, fontFamily: 'var(--sb-font-display)', fontSize: 26, fontWeight: 500, letterSpacing: '-0.02em' }}>
          Module coming online…
        </h1>
        <p style={{ marginTop: 10, color: 'var(--sb-fg-4)', fontSize: 13, lineHeight: 1.6 }}>
          The foundation shell is live. A module agent will wire this page up
          next — screens, data, and Lara hand-offs drop in here.
        </p>
        <div style={{
          marginTop: 20, fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-5)',
        }}>
          ▸ src/modules/{mod.toLowerCase()}/
        </div>
      </SBCard>
    </div>
  );
}
