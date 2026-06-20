import React, { useEffect } from 'react';
import { useLaraUI } from '../../lib/LaraUIContext.jsx';
import LaraDrawer from '../../modules/lara/components/LaraDrawer.jsx';

// The Lara side-drawer shell.
// Responsibility: backdrop + panel animation + Esc-to-close.
// Body is owned by the Lara module via `<LaraDrawer />`.

const DRAWER_WIDTH = 520;

export default function LaraDrawerShell() {
  const { open, seed, closeDrawer } = useLaraUI();

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === 'Escape') closeDrawer(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, closeDrawer]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={closeDrawer}
        style={{
          position: 'fixed', inset: 0, zIndex: 90,
          background: 'rgba(0,0,0,0.5)',
          backdropFilter: 'blur(2px)',
          animation: 'sb-fade-in 200ms ease',
        }}
      />
      {/* Panel */}
      <aside
        role="dialog"
        aria-label="Lara"
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0,
          width: DRAWER_WIDTH, maxWidth: '92vw',
          background: 'var(--sb-bg-2)', borderLeft: '1px solid var(--sb-line-2)',
          zIndex: 91, display: 'flex', flexDirection: 'column',
          boxShadow: '-40px 0 80px rgba(0,0,0,0.6)',
          animation: 'sb-slide-in 280ms var(--ease-out-quint, cubic-bezier(0.16, 1, 0.3, 1))',
        }}
      >
        <LaraDrawer seed={seed} onClose={closeDrawer} variant="drawer" />
      </aside>
    </>
  );
}
