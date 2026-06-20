import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBCard, SBChip, SBIcon, SBSkeleton } from '../../../components/primitives';
import api from '../../../lib/api.js';
import OfflineBanner from '../components/OfflineBanner.jsx';

const CHANNEL_ICONS = { email: 'mail', whatsapp: 'phone', linkedin: 'linkedin', sms: 'phone' };

export default function Channels() {
  const navigate = useNavigate();
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get('/api/automations/channels');
        if (!cancelled) { setChannels(r?.items || []); setError(null); }
      } catch (e) {
        if (cancelled) return;
        if (e.code === 'unauthenticated') { navigate('/admin/login'); return; }
        setError(e);
        setChannels([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [navigate]);

  return (
    <div>
      {error && <OfflineBanner code={error.code} />}
      <div style={{ padding: '28px 32px', maxWidth: 1100 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 6 }}>
          <h1 style={{
            fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 600,
            letterSpacing: '-0.02em', margin: 0,
          }}>Channels</h1>
          <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-5)' }}>
            {channels.length} registered
          </span>
        </div>
        <p style={{
          fontSize: 13, color: 'var(--sb-fg-4)', margin: '0 0 24px', maxWidth: 720, lineHeight: 1.6,
        }}>
          Channel adapters registered at boot. Email is live (Resend). The other three are
          registered stubs — the framework is pluggable, these rows prove it's not slideware.
        </p>

        {loading && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
            {Array.from({ length: 4 }).map((_, i) => (
              <SBSkeleton key={i} variant="card" h={120} style={{ opacity: Math.max(0.3, 1 - i * 0.18) }} />
            ))}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
          {channels.map((c) => {
            const active = c.status === 'active';
            return (
              <SBCard
                key={c.name}
                style={{ padding: 22, display: 'flex', flexDirection: 'column', gap: 14 }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{
                    width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: active ? 'var(--sb-accent-bg)' : 'var(--sb-panel)',
                    border: `1px solid ${active ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
                    color: active ? 'var(--sb-accent)' : 'var(--sb-fg-4)',
                  }}>
                    <SBIcon name={CHANNEL_ICONS[c.name] || 'bolt'} size={16} stroke={1.6} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontFamily: 'var(--sb-font-display)', fontSize: 17, fontWeight: 600,
                      textTransform: 'capitalize', letterSpacing: '-0.01em',
                    }}>{c.name}</div>
                    <div style={{
                      fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-5)',
                    }}>
                      provider: {c.provider}
                    </div>
                  </div>
                  <SBChip tone={active ? 'accent' : 'muted'} icon="dot">{c.status}</SBChip>
                </div>

                <div>
                  <div className="sb-label" style={{ marginBottom: 6 }}>Capabilities</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {(c.capabilities || []).map((cap) => (
                      <SBChip key={cap} tone={active ? 'cool' : 'muted'}>{cap}</SBChip>
                    ))}
                  </div>
                </div>

                {c.note && (
                  <div style={{
                    fontSize: 12, color: 'var(--sb-fg-4)', lineHeight: 1.55,
                    borderTop: '1px solid var(--sb-line)', paddingTop: 12,
                  }}>
                    {c.note}
                  </div>
                )}
              </SBCard>
            );
          })}
        </div>
      </div>
    </div>
  );
}
