import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBChip, SBIcon } from '../../components/primitives';
import api from '../../lib/api.js';
import { toast } from '../leads/lib/toast.jsx';

// First-send wizard — single overlay flow that turns "ICP → first email
// queued" into a 60-second guided path. Replaces the multi-page tour
// the flow audit flagged as the day-1 friction point.
//
// Steps:
//   0. ICP confirm     — ensure ICP is set; if not, link to wizard
//   1. Pick top leads  — show top-scored leads, user multi-selects
//   2. Generate openers — bulk-LLM generate openers for selected
//   3. Pick template   — choose first sequence template
//   4. Send            — fire bulk start_run, show summary
//
// Compact, focused, and skippable at any step. Never blocks the user
// from leaving the wizard — closes drop them on /admin/leads.

export default function FirstSendWizard({ onClose }) {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [icp, setIcp] = useState(null);
  const [leads, setLeads] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [templates, setTemplates] = useState([]);
  const [chosenTemplate, setChosenTemplate] = useState('');
  const [busy, setBusy] = useState(false);

  // Step 0: load ICP + check it's set.
  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/api/workspace/settings', { fresh: true });
        setIcp(r?.icp_description || '');
      } catch {
        setIcp('');
      }
    })();
  }, []);

  // Step 1: load top hot leads.
  useEffect(() => {
    if (step !== 1 || leads !== null) return;
    (async () => {
      try {
        const r = await api.get('/api/leads?min_score=60&limit=10');
        setLeads(r?.items || []);
      } catch {
        setLeads([]);
      }
    })();
  }, [step, leads]);

  // Step 3: load templates.
  useEffect(() => {
    if (step !== 3 || templates.length > 0) return;
    (async () => {
      try {
        const r = await api.get('/api/automations/templates');
        const items = r?.items || [];
        setTemplates(items);
        if (items[0]) setChosenTemplate(items[0].id);
      } catch {
        setTemplates([]);
      }
    })();
  }, [step, templates.length]);

  const draftOpeners = async () => {
    setBusy(true);
    try {
      const r = await api.post('/api/leads/bulk/opening-lines', {
        lead_ids: Array.from(selected), force: false,
      });
      const s = r?.summary || {};
      const parts = [];
      if (s.generated) parts.push(`${s.generated} drafted`);
      if (s.cached) parts.push(`${s.cached} cached`);
      if (s.skipped_no_signal) parts.push(`${s.skipped_no_signal} skipped`);
      toast.success(parts.join(' · ') || 'Done');
      setStep(3);
    } catch (err) {
      toast.error(err?.message || 'Drafting failed');
    } finally {
      setBusy(false);
    }
  };

  const fireSequences = async () => {
    if (!chosenTemplate) return;
    setBusy(true);
    let fired = 0, failed = 0;
    for (const id of selected) {
      try {
        await api.post('/api/automations/runs', {
          lead_id: id, template_id: chosenTemplate, created_by: 'first-send-wizard',
        });
        fired += 1;
      } catch {
        failed += 1;
      }
    }
    setBusy(false);
    if (fired > 0) {
      toast.success(`Sequence started for ${fired} lead${fired === 1 ? '' : 's'}${failed ? ` · ${failed} failed` : ''}`);
    } else {
      toast.error('No sequences started');
    }
    onClose?.();
    navigate('/admin/automations');
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 50,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-2)',
        width: 640, maxWidth: '94%', maxHeight: '90vh', overflow: 'auto',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 22px', borderBottom: '1px solid var(--sb-line)',
          display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <span className="sb-label" style={{ color: 'var(--sb-accent)' }}>First send · 60s</span>
          <Stepper step={step} />
          <div style={{ flex: 1 }} />
          <button onClick={onClose}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--sb-fg-4)' }}>
            <SBIcon name="close" size={14} />
          </button>
        </div>

        <div style={{ padding: 22, flex: 1 }}>
          {step === 0 && (
            <Step title="Confirm your ICP" hint="The single highest-leverage knob — your ICP description tunes the LLM's lead scoring.">
              {icp ? (
                <>
                  <div style={{ padding: 14, background: 'var(--sb-panel)', border: '1px solid var(--sb-line-2)',
                                fontSize: 12.5, fontFamily: 'var(--sb-font-mono)', whiteSpace: 'pre-wrap',
                                lineHeight: 1.55, maxHeight: 180, overflow: 'auto' }}>
                    {icp}
                  </div>
                  <div style={{ marginTop: 12, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                    <SBButton variant="ghost" size="sm" onClick={() => navigate('/admin/settings')}>
                      Edit ICP
                    </SBButton>
                    <SBButton variant="primary" size="sm" iconRight="arrow" onClick={() => setStep(1)}>
                      Looks good
                    </SBButton>
                  </div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 13, color: 'var(--sb-fg-3)', lineHeight: 1.55, marginBottom: 12 }}>
                    Your ICP isn't set yet. Set it in Settings, then come back —
                    scoring won't work without it.
                  </div>
                  <SBButton variant="primary" size="sm" iconRight="arrow"
                    onClick={() => navigate('/admin/settings')}>
                    Set ICP
                  </SBButton>
                </>
              )}
            </Step>
          )}

          {step === 1 && (
            <Step title="Pick the leads to send to"
                  hint="These are your highest-scored leads. Select the ones to send first; rest stay in your pipeline.">
              {leads === null && <div style={{ color: 'var(--sb-fg-5)', fontSize: 12, fontFamily: 'var(--sb-font-mono)' }}>▸ loading…</div>}
              {leads && leads.length === 0 && (
                <div style={{ fontSize: 13, color: 'var(--sb-fg-4)', lineHeight: 1.55 }}>
                  No leads above 60 yet. Run a scraper or import a CSV first.
                  <div style={{ marginTop: 12 }}>
                    <SBButton variant="primary" size="sm" onClick={() => navigate('/admin/scrapers')}>
                      Go to scrapers
                    </SBButton>
                  </div>
                </div>
              )}
              {leads && leads.length > 0 && (
                <>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 320, overflow: 'auto' }}>
                    {leads.map((l) => {
                      const score = (typeof l.score === 'object' ? l.score?.value : l.score) ?? 0;
                      const checked = selected.has(l.id);
                      return (
                        <label key={l.id} style={{
                          display: 'grid', gridTemplateColumns: '24px 1fr auto',
                          gap: 10, padding: '8px 10px', alignItems: 'center',
                          background: checked ? 'var(--sb-accent-bg)' : 'var(--sb-panel)',
                          border: `1px solid ${checked ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
                          cursor: 'pointer',
                        }}>
                          <input type="checkbox" checked={checked}
                            onChange={() => setSelected((s) => {
                              const n = new Set(s);
                              if (n.has(l.id)) n.delete(l.id); else n.add(l.id);
                              return n;
                            })} />
                          <div>
                            <div style={{ fontSize: 13, color: 'var(--sb-fg)' }}>{l.name || l.email || '(unnamed)'}</div>
                            <div style={{ fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
                              {l.company || ''} {l.email ? `· ${l.email}` : ''}
                            </div>
                          </div>
                          <span style={{
                            fontSize: 14, fontFamily: 'var(--sb-font-mono)', fontWeight: 600,
                            color: score >= 80 ? 'var(--sb-hot)' : 'var(--sb-warm)',
                          }}>{score}</span>
                        </label>
                      );
                    })}
                  </div>
                  <div style={{ marginTop: 14, display: 'flex', gap: 8, justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
                      {selected.size} selected
                    </span>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <SBButton variant="ghost" size="sm" onClick={() => setStep(0)}>Back</SBButton>
                      <SBButton variant="primary" size="sm" iconRight="arrow"
                        disabled={selected.size === 0}
                        onClick={() => setStep(2)}>
                        Next ({selected.size})
                      </SBButton>
                    </div>
                  </div>
                </>
              )}
            </Step>
          )}

          {step === 2 && (
            <Step title="Draft personalized openers"
                  hint="One AI-generated sentence per lead, grounded in their source signal. Skipped leads with no signal still send the template body.">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <SBChip tone="accent" icon="spark">{selected.size} leads</SBChip>
                <span style={{ fontSize: 11.5, color: 'var(--sb-fg-5)' }}>
                  ~{selected.size * 2}-{selected.size * 5}s
                </span>
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <SBButton variant="ghost" size="sm" onClick={() => setStep(1)}>Back</SBButton>
                <SBButton variant="ghost" size="sm" onClick={() => setStep(3)}>Skip</SBButton>
                <SBButton variant="primary" size="sm" icon="bolt" disabled={busy}
                  onClick={draftOpeners}>
                  {busy ? 'Drafting…' : 'Draft openers'}
                </SBButton>
              </div>
            </Step>
          )}

          {step === 3 && (
            <Step title="Pick a sequence template"
                  hint="Day-0 send fires now (or per send-time optimization), follow-ups land per the template's cadence.">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
                {templates.length === 0 && (
                  <div style={{ fontSize: 12, color: 'var(--sb-fg-5)' }}>No templates loaded yet…</div>
                )}
                {templates.map((t) => (
                  <label key={t.id} style={{
                    display: 'flex', gap: 10, padding: '10px 12px', alignItems: 'center',
                    background: chosenTemplate === t.id ? 'var(--sb-accent-bg)' : 'var(--sb-panel)',
                    border: `1px solid ${chosenTemplate === t.id ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
                    cursor: 'pointer',
                  }}>
                    <input type="radio" name="tpl" checked={chosenTemplate === t.id}
                      onChange={() => setChosenTemplate(t.id)} />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{t.name || t.key}</div>
                      <div style={{ fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
                        {t.key}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <SBButton variant="ghost" size="sm" onClick={() => setStep(2)}>Back</SBButton>
                <SBButton variant="primary" size="sm" icon="bolt" disabled={busy || !chosenTemplate}
                  onClick={fireSequences}>
                  {busy ? `Firing ${selected.size}…` : `Send to ${selected.size}`}
                </SBButton>
              </div>
            </Step>
          )}
        </div>
      </div>
    </div>
  );
}

function Stepper({ step }) {
  const steps = ['ICP', 'Leads', 'Openers', 'Send'];
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      {steps.map((s, i) => (
        <span key={s} style={{
          padding: '3px 8px', fontSize: 10, fontFamily: 'var(--sb-font-mono)',
          textTransform: 'uppercase', letterSpacing: '0.06em',
          background: i === step ? 'var(--sb-accent-bg)' : 'transparent',
          border: `1px solid ${i === step ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
          color: i === step ? 'var(--sb-accent)' : (i < step ? 'var(--sb-fg-3)' : 'var(--sb-fg-5)'),
        }}>{i + 1} · {s}</span>
      ))}
    </div>
  );
}

function Step({ title, hint, children }) {
  return (
    <div>
      <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>{title}</div>
      {hint && (
        <div style={{ fontSize: 12.5, color: 'var(--sb-fg-4)', lineHeight: 1.55, marginBottom: 18 }}>
          {hint}
        </div>
      )}
      {children}
    </div>
  );
}
