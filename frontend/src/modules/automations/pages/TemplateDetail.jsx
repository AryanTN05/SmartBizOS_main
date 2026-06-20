import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { SBButton, SBCard, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import TimelineStep from '../components/TimelineStep.jsx';
import OfflineBanner from '../components/OfflineBanner.jsx';
import StartRunModal from '../components/StartRunModal.jsx';
import { formatDuration } from '../lib/format.js';

export default function TemplateDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [startOpen, setStartOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const r = await api.get(`/api/automations/templates/${id}`);
        if (!cancelled) { setData(r); setError(null); }
      } catch (e) {
        if (cancelled) return;
        if (e.code === 'unauthenticated') { navigate('/admin/login'); return; }
        setError(e);
        setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [id, navigate]);

  if (loading && !data) {
    return (
      <div style={{ padding: 40, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', fontSize: 12 }}>
        ▸ loading template…
      </div>
    );
  }
  if (!data) return null;

  const { template, steps = [], placeholder_schema = [], previews = [] } = data;
  const previewByOrder = new Map(previews.map((p) => [p.step_order, p]));

  // Build TimelineStep-shape rows from the static template definition.
  const timelineSteps = steps.map((s) => ({
    name: s.description || s.template_key || `step_${s.order}`,
    kind: s.kind === 'send' ? 'send' : s.kind,
    order: s.order,
    channel: s.channel,
    duration: s.kind === 'wait' ? formatDuration(s.wait_duration_seconds) : null,
    detail: s.branch_on ? `branch on ${s.branch_on}` : null,
    description: s.description,
  }));

  return (
    <div>
      {error && <OfflineBanner code={error.code} />}
      <div style={{ padding: '28px 32px', maxWidth: 1100 }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <button
            onClick={() => navigate('/admin/automations/templates')}
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: 'var(--sb-fg-4)', display: 'inline-flex', alignItems: 'center', gap: 4,
              fontFamily: 'var(--sb-font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.1em',
            }}
          >
            <span style={{ display: 'inline-flex', transform: 'rotate(180deg)' }}>
              <SBIcon name="chevronR" size={11} stroke={2} />
            </span>
            Templates
          </button>
          <span style={{ color: 'var(--sb-fg-6)' }}>/</span>
          <span className="sb-label" style={{ color: 'var(--sb-accent)' }}>{template.key}</span>
          <SBChip tone={template.status === 'active' ? 'accent' : 'muted'} icon="dot">{template.status}</SBChip>
          <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-5)' }}>
            · {template.version}
          </span>
          <div style={{ flex: 1 }} />
          <SBButton variant="primary" size="sm" icon="bolt" onClick={() => setStartOpen(true)}>
            Start run with this template
          </SBButton>
        </div>

        <h1 style={{
          fontFamily: 'var(--sb-font-display)', fontSize: 32, fontWeight: 600,
          letterSpacing: '-0.02em', margin: '10px 0 6px',
        }}>{template.name}</h1>
        <p style={{
          fontSize: 14, color: 'var(--sb-fg-3)', margin: '0 0 24px', lineHeight: 1.6, maxWidth: 760,
        }}>{template.description}</p>

        {/* Meta row */}
        <div style={{ display: 'flex', gap: 16, marginBottom: 28, flexWrap: 'wrap' }}>
          <MetaItem label="Steps" value={template.step_count} />
          <MetaItem label="Channels" value={(template.channels_used || []).join(', ') || '—'} />
          <MetaItem label="Placeholders" value={placeholder_schema.length} />
          <MetaItem label="Previews" value={previews.length} />
        </div>

        {/* Flow */}
        <div className="sb-label" style={{ marginBottom: 12 }}>Flow</div>
        <div style={{ background: 'var(--sb-card)', border: '1px solid var(--sb-line)', marginBottom: 28 }}>
          {timelineSteps.map((s, i) => (
            <TimelineStep key={i} step={s} last={i === timelineSteps.length - 1} static />
          ))}
        </div>

        {/* Placeholder schema */}
        {placeholder_schema.length > 0 && (
          <>
            <div className="sb-label" style={{ marginBottom: 10 }}>Placeholder schema</div>
            <div style={{ display: 'flex', gap: 6, marginBottom: 28, flexWrap: 'wrap' }}>
              {placeholder_schema.map((p) => (
                <code key={p} style={{
                  fontFamily: 'var(--sb-font-mono)', fontSize: 11,
                  background: 'var(--sb-panel)', border: '1px solid var(--sb-line-2)',
                  padding: '3px 8px', color: 'var(--sb-fg-2)',
                }}>{p}</code>
              ))}
            </div>
          </>
        )}

        {/* Email previews */}
        {previews.length > 0 && (
          <>
            <div className="sb-label" style={{ marginBottom: 12 }}>Email previews</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {steps.filter((s) => s.kind === 'send').map((step) => {
                const p = previewByOrder.get(step.order);
                if (!p) return null;
                return (
                  <SBCard key={step.order} style={{ padding: 0, overflow: 'hidden' }}>
                    <div style={{
                      padding: '12px 18px', borderBottom: '1px solid var(--sb-line)',
                      background: 'var(--sb-panel)',
                      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                    }}>
                      <span className="sb-label">Step {step.order + 1}</span>
                      <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-4)' }}>
                        {p.template_key}
                      </span>
                      <SBChip tone="cool">{p.channel}</SBChip>
                      <div style={{ flex: 1 }} />
                    </div>
                    {p.subject && (
                      <div style={{
                        padding: '12px 18px', borderBottom: '1px solid var(--sb-line)',
                        display: 'flex', gap: 10, alignItems: 'baseline',
                      }}>
                        <span className="sb-label">Subject</span>
                        <span style={{ fontSize: 13, fontWeight: 600 }}>{p.subject}</span>
                      </div>
                    )}
                    <div
                      style={{
                        padding: '18px 22px', fontSize: 13.5, lineHeight: 1.65,
                        color: 'var(--sb-fg-2)', maxHeight: 300, overflow: 'auto',
                      }}
                      dangerouslySetInnerHTML={{ __html: p.body_html || '' }}
                    />
                  </SBCard>
                );
              })}
            </div>
          </>
        )}
      </div>

      <StartRunModal
        open={startOpen}
        templateId={template.id}
        onClose={() => setStartOpen(false)}
        onRunCreated={(run) => run?.id && navigate(`/admin/automations/${run.id}`)}
      />
    </div>
  );
}

function MetaItem({ label, value }) {
  return (
    <div style={{
      padding: '12px 18px', background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
      minWidth: 120,
    }}>
      <div className="sb-label" style={{ marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 500, fontFamily: 'var(--sb-font-mono)', color: 'var(--sb-fg)' }}>
        {value}
      </div>
    </div>
  );
}
