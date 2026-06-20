import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBCard, SBChip, SBButton, SBSkeleton } from '../../../components/primitives';
import api from '../../../lib/api.js';
import OfflineBanner from '../components/OfflineBanner.jsx';
import StartRunModal from '../components/StartRunModal.jsx';

// Templates list — cards for each registered template.
// Click → /templates/:id detail. "Start run" opens StartRunModal pre-filled.
export default function Templates() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modal, setModal] = useState({ open: false, templateId: null });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get('/api/automations/templates');
        if (!cancelled) {
          setTemplates(r?.items || []);
          setError(null);
        }
      } catch (e) {
        if (cancelled) return;
        if (e.code === 'unauthenticated') { navigate('/admin/login'); return; }
        setError(e);
        setTemplates([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [navigate]);

  return (
    <div>
      {error && <OfflineBanner code={error.code} />}
      <div style={{ padding: '28px 32px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 20 }}>
          <h1 style={{
            fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 600,
            letterSpacing: '-0.02em', margin: 0,
          }}>Templates</h1>
          <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-5)' }}>
            {templates.length} active
          </span>
          <div style={{ flex: 1 }} />
          <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-5)' }}>
            code-as-template · read-only in V0
          </span>
        </div>

        {loading && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
            {Array.from({ length: 3 }).map((_, i) => (
              <SBSkeleton key={i} variant="card" h={140} style={{ opacity: Math.max(0.3, 1 - i * 0.2) }} />
            ))}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
          {templates.map((t) => (
            <SBCard
              key={t.id}
              hover
              onClick={() => navigate(`/admin/automations/templates/${t.id}`)}
              style={{ padding: 22, display: 'flex', flexDirection: 'column', gap: 12 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="sb-label" style={{ color: 'var(--sb-accent)', fontFamily: 'var(--sb-font-mono)' }}>
                  {t.key}
                </span>
                <div style={{ flex: 1 }} />
                <SBChip tone={t.status === 'active' ? 'accent' : 'muted'} icon="dot">{t.status}</SBChip>
              </div>
              <div style={{
                fontFamily: 'var(--sb-font-display)', fontSize: 18, fontWeight: 600,
                letterSpacing: '-0.01em',
              }}>{t.name}</div>
              <div style={{
                fontSize: 12.5, color: 'var(--sb-fg-3)', lineHeight: 1.55,
                display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
              }}>{t.description}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 'auto' }}>
                <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-4)' }}>
                  {t.step_count} steps
                </span>
                <span style={{ color: 'var(--sb-fg-5)' }}>·</span>
                {(t.channels_used || []).map((c) => (
                  <SBChip key={c} tone="cool">{c}</SBChip>
                ))}
                <div style={{ flex: 1 }} />
                <SBButton
                  variant="ghost"
                  size="xs"
                  icon="bolt"
                  onClick={(e) => { e.stopPropagation(); setModal({ open: true, templateId: t.id }); }}
                >
                  Start run
                </SBButton>
              </div>
            </SBCard>
          ))}
        </div>
      </div>

      <StartRunModal
        open={modal.open}
        templateId={modal.templateId}
        onClose={() => setModal({ open: false, templateId: null })}
        onRunCreated={(run) => run?.id && navigate(`/admin/automations/${run.id}`)}
      />
    </div>
  );
}
