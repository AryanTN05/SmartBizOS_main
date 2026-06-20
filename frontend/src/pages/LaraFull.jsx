import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBIcon } from '../components/primitives';
import { DemoCountdown } from '../components/chrome';
import { useSession } from '../lib/SessionContext.jsx';
import { useLaraUI } from '../lib/LaraUIContext.jsx';

// Demo-facing Lara page at /lara.
//
// This is the page demo visitors land on after clicking "Try the 5-min demo".
// Admins also get a stub at /admin/lara, but /lara is the canonical,
// demo-accessible URL (per scaffold brief: pick the cleanest, be consistent).
//
// We auto-open the drawer on mount so the user arrives mid-conversation.
// The Lara module agent will likely replace this wrapper with a full
// split-view (drawer left, tool-log right), but the contract with the
// foundation is: import `useLaraUI()` and render whatever you want.
export default function LaraFull() {
  const navigate = useNavigate();
  const { session } = useSession();
  const { openDrawer } = useLaraUI();

  useEffect(() => {
    // Visitors with no session (e.g. backend offline) still see the chrome.
    if (session?.kind === 'anon' && window.location.pathname === '/lara') {
      // Don't force back — let them stay; drawer explains the state.
    }
    openDrawer();
  }, [openDrawer, session]);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--sb-bg)' }}>
      <header style={{
        padding: '14px 28px', borderBottom: '1px solid var(--sb-line)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 32, height: 32, background: 'var(--sb-accent)', color: '#000',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--sb-font-display)', fontSize: 18, fontWeight: 700, letterSpacing: '-0.04em',
          }}>sb</div>
          <div>
            <div style={{ fontFamily: 'var(--sb-font-display)', fontSize: 14, fontWeight: 600 }}>SmartBiz OS</div>
            <div className="sb-label">demo · lara</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <DemoCountdown />
          <SBButton variant="ghost" size="sm" onClick={() => navigate('/')}>Exit demo</SBButton>
        </div>
      </header>

      <main style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 28 }}>
        <div style={{ maxWidth: 520, textAlign: 'center' }}>
          <div style={{
            width: 56, height: 56, background: 'var(--sb-accent-bg)', color: 'var(--sb-accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 18px',
          }}>
            <SBIcon name="lara" size={24} stroke={1.3} />
          </div>
          <h1 style={{
            fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 500,
            letterSpacing: '-0.02em', margin: 0,
          }}>
            Ask Lara anything.
          </h1>
          <p style={{ marginTop: 10, color: 'var(--sb-fg-3)', fontSize: 14, lineHeight: 1.6 }}>
            The conversation panel opened on the right. Try: <span className="sb-mono sb-accent">"anything hot this morning?"</span>
          </p>
          <div style={{ marginTop: 18 }}>
            <SBButton variant="outline" size="sm" icon="lara" onClick={() => openDrawer()}>
              Reopen Lara
            </SBButton>
          </div>
        </div>
      </main>
    </div>
  );
}
