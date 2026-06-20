import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBChip } from '../components/primitives';
import { useSession } from '../lib/SessionContext.jsx';

// Public splash. Ported from `ui_kits/smartbiz/SignIn.jsx`.
export default function DemoLanding() {
  const navigate = useNavigate();
  const { session, ready, initDemo } = useSession();

  // Only punt inward AFTER /api/session/me resolves. Without the `ready`
  // gate, the FALLBACK_SESSION (admin under VITE_AUTH_BYPASS) made every
  // first-time visitor instantly bounce to /admin → /admin/login, never
  // seeing the public landing.
  useEffect(() => {
    if (!ready) return;
    if (session?.kind === 'demo') navigate('/lara', { replace: true });
    if (session?.kind === 'admin') navigate('/admin', { replace: true });
  }, [ready, session, navigate]);

  const onDemo = async () => {
    try { await initDemo(); } catch (_) { /* backend offline, still navigate so the UI is explorable */ }
    navigate('/lara');
  };
  const onSignIn = () => navigate('/admin/login');

  return (
    <div style={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: '1fr 1fr', background: 'var(--sb-bg)' }}>
      <div style={{ padding: '48px 56px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minHeight: '100vh' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 32, height: 32, background: 'var(--sb-accent)', color: '#000',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--sb-font-display)', fontSize: 18, fontWeight: 700, letterSpacing: '-0.04em',
          }}>sb</div>
          <div>
            <div style={{ fontFamily: 'var(--sb-font-display)', fontSize: 16, fontWeight: 600, letterSpacing: '-0.01em' }}>SmartBiz OS</div>
            <div style={{ fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', letterSpacing: '0.1em' }}>by zero → prod</div>
          </div>
        </div>

        <div style={{ maxWidth: 420 }}>
          <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ width: 24, height: 1, background: 'var(--sb-accent)' }} /> The AI business OS
          </div>
          <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 52, fontWeight: 500, letterSpacing: '-0.035em', lineHeight: 1.02, margin: '0 0 18px' }}>
            Every module.<br />
            One brain.<br />
            <span style={{ color: 'var(--sb-accent)' }}>Lara.</span>
          </h1>
          <p style={{ fontSize: 15, color: 'var(--sb-fg-3)', margin: '0 0 32px', lineHeight: 1.55 }}>
            Leads, sequences, reports, docs — all wired to one conversational layer. Ask Lara anything. It reads. It writes. It acts.
          </p>

          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <SBButton variant="primary" size="lg" icon="bolt" onClick={onDemo}>Try the 5-min demo</SBButton>
            <SBButton variant="ghost" size="lg" onClick={onSignIn}>Sign in</SBButton>
          </div>

          <div style={{ marginTop: 32, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 11.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
            <div>▸ anonymous · no email · 2000 tokens · 1 session / IP / hour</div>
            <div>▸ seed data only · nothing you do will send real emails</div>
          </div>
        </div>

        <div style={{ fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', letterSpacing: '0.12em' }}>
          V0 · ZERO → PROD · MCP-first
        </div>
      </div>

      <div style={{ borderLeft: '1px solid var(--sb-line)', background: 'var(--sb-bg-2)', position: 'relative', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <div style={{ position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(#888 1px, transparent 1px), linear-gradient(90deg, #888 1px, transparent 1px)', backgroundSize: '48px 48px', opacity: 0.04, maskImage: 'radial-gradient(ellipse 60% 60% at 50% 50%, black 20%, transparent 100%)' }} />
        <div style={{ position: 'relative', width: '100%', maxWidth: 460, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="sb-brackets" style={{ padding: 18, background: 'var(--sb-card)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, fontFamily: 'var(--sb-font-mono)', fontSize: 11 }}>
              <span style={{ color: 'var(--sb-fg-5)' }}>▸</span>
              <span style={{ color: 'var(--sb-fg-3)' }}>"anything hot this morning?"</span>
            </div>
            <div style={{ padding: 12, background: 'var(--sb-bg-2)', border: '1px solid var(--sb-line)', fontFamily: 'var(--sb-font-mono)', fontSize: 11, marginBottom: 10 }}>
              <div style={{ color: 'var(--sb-violet)' }}>▸ get_leads <span style={{ color: 'var(--sb-fg-5)' }}>{'{ since: \'24h\' }'}</span></div>
              <div style={{ color: 'var(--sb-accent)', marginTop: 4 }}>✓ 3 leads · scores 82, 79, 77</div>
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--sb-fg-2)', lineHeight: 1.55 }}>
              3 leads crossed into hot overnight. Priya is the strongest — repeat pricing visitor, tried the sandbox. Want me to start a warm outbound?
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {['M1 Lara', 'M2 Sales Intel', 'M3 Automation', 'M6 Reports', 'Docs + RAG'].map((x) => (
              <SBChip key={x} tone="muted">{x}</SBChip>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
