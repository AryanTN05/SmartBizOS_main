import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBIcon } from '../../../components/primitives';
import { DemoCountdown } from '../../../components/chrome';
import { useSession } from '../../../lib/SessionContext.jsx';
import { useLaraUI } from '../../../lib/LaraUIContext.jsx';
import api from '../../../lib/api.js';
import LaraDrawer from '../components/LaraDrawer.jsx';
import EmptyState from '../components/EmptyState.jsx';

// Full-page Lara chat. Used by:
//   - /lara          (demo-facing) — simple header + centered chat
//   - /admin/lara    (admin)       — conversation rail on left, chat on right
//
// The `mode` prop controls which variant renders. For admins we fetch a
// conversation sidebar; if that 404s we degrade gracefully to the empty state.
export default function LaraFull({ mode = 'demo' }) {
  const navigate = useNavigate();
  const { session } = useSession();
  const { closeDrawer } = useLaraUI();

  // The drawer shell auto-mounts on /admin/* via App.jsx. Close it when the
  // full-page experience is active so it doesn't overlay.
  useEffect(() => { closeDrawer(); }, [closeDrawer]);

  if (mode === 'admin') {
    return <AdminFullPage />;
  }
  return <DemoFullPage session={session} navigate={navigate} />;
}

// ─── Demo full-page ──────────────────────────────────────────────────────────
function DemoFullPage({ session, navigate }) {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      background: 'var(--sb-bg)',
    }}>
      <header style={{
        padding: '14px 28px', borderBottom: '1px solid var(--sb-line)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20,
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 32, height: 32, background: 'var(--sb-accent)', color: '#000',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--sb-font-display)', fontSize: 18, fontWeight: 700,
            letterSpacing: '-0.04em',
          }}>sb</div>
          <div>
            <div style={{ fontFamily: 'var(--sb-font-display)', fontSize: 14, fontWeight: 600 }}>
              SmartBiz OS
            </div>
            <div className="sb-label">demo · lara</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {session?.kind === 'demo' && <DemoCountdown />}
          <SBButton variant="ghost" size="sm" onClick={() => navigate('/')}>Exit demo</SBButton>
        </div>
      </header>

      <main style={{
        flex: 1, minHeight: 0, display: 'flex', justifyContent: 'center',
        padding: '24px 24px 0',
      }}>
        <div style={{
          width: '100%', maxWidth: 860, display: 'flex', flexDirection: 'column',
          border: '1px solid var(--sb-line)', borderBottom: 'none',
        }}>
          <LaraDrawer variant="page" />
        </div>
      </main>
    </div>
  );
}

// ─── Admin full-page ─────────────────────────────────────────────────────────
function AdminFullPage() {
  const [convos, setConvos] = useState(null); // null=loading, []=empty, Array=list, false=error
  const [activeId, setActiveId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get('/api/conversations?limit=20');
        if (!cancelled) setConvos(r?.items || []);
      } catch (e) {
        if (!cancelled) setConvos(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <div style={{
      height: 'calc(100vh - 56px)', // topbar height; leave room for chrome
      display: 'flex', minHeight: 0,
    }}>
      <aside style={{
        width: 280, borderRight: '1px solid var(--sb-line)',
        background: 'var(--sb-bg-2)', display: 'flex', flexDirection: 'column',
        minHeight: 0,
      }}>
        <div style={{
          padding: '14px 16px', borderBottom: '1px solid var(--sb-line)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div className="sb-label">conversations</div>
          <SBButton variant="ghost" size="xs" icon="plus" onClick={() => setActiveId(null)}>
            New
          </SBButton>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
          {convos === null && (
            <div style={{
              padding: 16, fontSize: 11, fontFamily: 'var(--sb-font-mono)',
              color: 'var(--sb-fg-5)',
            }}>loading…</div>
          )}
          {convos === false && (
            <div style={{ padding: 8 }}>
              <EmptyState detail="Conversations endpoint isn't online yet." />
            </div>
          )}
          {Array.isArray(convos) && convos.length === 0 && (
            <div style={{ padding: 8 }}>
              <EmptyState detail="No conversations yet. Start one on the right." />
            </div>
          )}
          {Array.isArray(convos) && convos.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveId(c.id)}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '10px 12px', marginBottom: 2,
                background: activeId === c.id ? 'var(--sb-card)' : 'transparent',
                border: `1px solid ${activeId === c.id ? 'var(--sb-line-2)' : 'transparent'}`,
                cursor: 'pointer', fontFamily: 'var(--sb-font)',
              }}
            >
              <div style={{
                fontSize: 12.5, color: 'var(--sb-fg)', fontWeight: 500,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>{c.title || 'Untitled'}</div>
              <div style={{
                fontSize: 10, color: 'var(--sb-fg-5)', marginTop: 3,
                fontFamily: 'var(--sb-font-mono)',
              }}>
                {c.message_count ?? 0} msgs · {c.kind}
              </div>
            </button>
          ))}
        </div>
      </aside>

      <section style={{ flex: 1, minWidth: 0, display: 'flex' }}>
        <LaraDrawer variant="page" showHeader />
      </section>
    </div>
  );
}
