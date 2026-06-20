import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { SBButton, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';

// Modal for starting a new automation run.
// Used from the runs list page ("Start run") and from the M2 lead drawer
// (which passes a `leadId` so the picker is pre-seeded).
//
// Props:
//   open: boolean
//   onClose: () => void
//   leadId?: string       — pre-fill the lead picker
//   templateId?: string   — pre-fill the template dropdown
//   onRunCreated?: (run) => void
export default function StartRunModal({ open, onClose, leadId, templateId, onRunCreated }) {
  const [leadQuery, setLeadQuery] = useState('');
  const [leads, setLeads] = useState([]);
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [selectedLeadId, setSelectedLeadId] = useState(leadId || '');
  const [selectedLead, setSelectedLead] = useState(null);

  const [templates, setTemplates] = useState([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState(templateId || '');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [conflict, setConflict] = useState(null); // { existing_run_id }
  const inputRef = useRef(null);

  // Reset local state on each open so the modal feels fresh.
  useEffect(() => {
    if (!open) return;
    setSelectedLeadId(leadId || '');
    setSelectedTemplateId(templateId || '');
    setError(null);
    setConflict(null);
    setLeadQuery('');
    setTimeout(() => inputRef.current?.focus(), 60);
  }, [open, leadId, templateId]);

  // Load templates once per open.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get('/api/automations/templates');
        if (!cancelled) setTemplates(r?.items || []);
      } catch (_e) {
        if (!cancelled) setTemplates([]);
      }
    })();
    return () => { cancelled = true; };
  }, [open]);

  // Resolve the currently-selected lead for the summary card.
  useEffect(() => {
    if (!selectedLeadId) { setSelectedLead(null); return; }
    // Try the in-memory list first so picking is instant.
    const cached = leads.find((l) => l.id === selectedLeadId);
    if (cached) { setSelectedLead(cached); return; }
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get(`/api/leads/${selectedLeadId}`);
        if (!cancelled && r) setSelectedLead(r);
      } catch (_e) {
        // Silent — the picker below will render without the summary card.
      }
    })();
    return () => { cancelled = true; };
  }, [selectedLeadId, leads]);

  // Debounced lead search.
  useEffect(() => {
    if (!open || selectedLeadId) return;
    const q = leadQuery.trim();
    let cancelled = false;
    setLeadsLoading(true);
    const handle = setTimeout(async () => {
      try {
        const url = `/api/leads?limit=20${q ? `&q=${encodeURIComponent(q)}` : ''}`;
        const r = await api.get(url);
        if (!cancelled) setLeads(r?.items || []);
      } catch (_e) {
        if (!cancelled) setLeads([]);
      } finally {
        if (!cancelled) setLeadsLoading(false);
      }
    }, 180);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [leadQuery, open, selectedLeadId]);

  if (!open) return null;

  const submit = async () => {
    if (!selectedLeadId || !selectedTemplateId) return;
    setSubmitting(true);
    setError(null);
    setConflict(null);
    try {
      const r = await api.post('/api/automations/runs', {
        lead_id: selectedLeadId,
        template_id: selectedTemplateId,
      });
      const run = r?.run || r;
      if (onRunCreated) onRunCreated(run);
      onClose?.();
    } catch (e) {
      if (e.status === 409 && e.details?.existing_run_id) {
        setConflict({ existing_run_id: e.details.existing_run_id });
      } else {
        setError(e);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50,
      }}
    >
      <div style={{
        width: 540, maxWidth: '92vw', maxHeight: '88vh', overflow: 'auto',
        background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-2)',
      }}>
        {/* Header */}
        <div style={{
          padding: '18px 22px', borderBottom: '1px solid var(--sb-line)',
          display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <span className="sb-label" style={{ color: 'var(--sb-accent)' }}>Start run</span>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--sb-fg-4)',
            display: 'inline-flex', padding: 4,
          }}><SBIcon name="close" size={14} stroke={1.8} /></button>
        </div>

        <div style={{ padding: 22, display: 'flex', flexDirection: 'column', gap: 18 }}>
          {/* Lead picker */}
          <div>
            <div className="sb-label" style={{ marginBottom: 8 }}>Lead</div>
            {selectedLead || (selectedLeadId && leadId) ? (
              <div style={{
                padding: '10px 12px', border: '1px solid var(--sb-line-2)',
                background: 'var(--sb-panel)', display: 'flex', alignItems: 'center', gap: 10,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>
                    {selectedLead
                      ? (selectedLead.name || `${selectedLead.first_name || ''} ${selectedLead.last_name || ''}`.trim() || selectedLead.email)
                      : selectedLeadId}
                  </div>
                  {selectedLead && (
                    <div style={{ fontSize: 11, color: 'var(--sb-fg-4)', fontFamily: 'var(--sb-font-mono)' }}>
                      {selectedLead.email}{selectedLead.company ? ` · ${selectedLead.company}` : ''}
                    </div>
                  )}
                </div>
                {!leadId && (
                  <SBButton variant="ghost" size="xs" onClick={() => { setSelectedLeadId(''); setSelectedLead(null); }}>
                    Change
                  </SBButton>
                )}
              </div>
            ) : (
              <>
                <input
                  ref={inputRef}
                  value={leadQuery}
                  onChange={(e) => setLeadQuery(e.target.value)}
                  placeholder="Search leads…"
                  style={{
                    width: '100%', padding: '9px 12px', fontSize: 13,
                    background: 'var(--sb-panel)', color: 'var(--sb-fg)',
                    border: '1px solid var(--sb-line-2)', outline: 'none',
                  }}
                  onFocus={(e) => e.target.style.borderColor = 'var(--sb-accent)'}
                  onBlur={(e) => e.target.style.borderColor = 'var(--sb-line-2)'}
                />
                <div style={{
                  marginTop: 6, maxHeight: 180, overflow: 'auto',
                  border: '1px solid var(--sb-line)',
                }}>
                  {leadsLoading && (
                    <div style={{ padding: 10, fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
                      searching…
                    </div>
                  )}
                  {!leadsLoading && leads.length === 0 && (
                    <div style={{ padding: 10, fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
                      no matches
                    </div>
                  )}
                  {leads.map((l) => (
                    <div
                      key={l.id}
                      onClick={() => { setSelectedLeadId(l.id); setSelectedLead(l); }}
                      style={{
                        padding: '8px 12px', borderBottom: '1px solid var(--sb-line)',
                        cursor: 'pointer',
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.background = 'var(--sb-panel)'}
                      onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                    >
                      <div style={{ fontSize: 12.5, fontWeight: 600 }}>
                        {l.name || `${l.first_name || ''} ${l.last_name || ''}`.trim() || l.email}
                      </div>
                      <div style={{ fontSize: 10.5, color: 'var(--sb-fg-4)', fontFamily: 'var(--sb-font-mono)' }}>
                        {l.email}{l.company ? ` · ${l.company}` : ''}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Template dropdown */}
          <div>
            <div className="sb-label" style={{ marginBottom: 8 }}>Template</div>
            <select
              value={selectedTemplateId}
              onChange={(e) => setSelectedTemplateId(e.target.value)}
              style={{
                width: '100%', padding: '9px 12px', fontSize: 13,
                background: 'var(--sb-panel)', color: 'var(--sb-fg)',
                border: '1px solid var(--sb-line-2)', outline: 'none',
                fontFamily: 'var(--sb-font)',
              }}
            >
              <option value="">— Pick a template —</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} · {t.step_count} steps
                </option>
              ))}
            </select>
          </div>

          {/* Conflict surface */}
          {conflict && (
            <div style={{
              padding: '10px 12px', background: 'rgba(255,181,71,0.08)',
              border: '1px solid var(--sb-warm)', fontSize: 12, color: 'var(--sb-fg-2)',
              display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
            }}>
              <SBChip tone="warm" icon="warn">Active run exists</SBChip>
              <span>An active run already exists for this lead + template.</span>
              <Link
                to={`/admin/automations/${conflict.existing_run_id}`}
                onClick={() => onClose?.()}
                style={{ color: 'var(--sb-accent)', textDecoration: 'none', fontFamily: 'var(--sb-font-mono)', fontSize: 11 }}
              >
                View existing →
              </Link>
            </div>
          )}

          {error && (
            <div style={{
              padding: '10px 12px', background: 'rgba(255,90,106,0.08)',
              border: '1px solid var(--sb-hot)', fontSize: 12, color: 'var(--sb-fg-2)',
            }}>
              <span style={{ color: 'var(--sb-hot)', fontFamily: 'var(--sb-font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                {error.code}
              </span>
              <span style={{ marginLeft: 8 }}>{error.message}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '14px 22px', borderTop: '1px solid var(--sb-line)',
          display: 'flex', justifyContent: 'flex-end', gap: 8,
        }}>
          <SBButton variant="ghost" size="sm" onClick={onClose}>Cancel</SBButton>
          <SBButton
            variant="primary"
            size="sm"
            icon="bolt"
            disabled={!selectedLeadId || !selectedTemplateId || submitting}
            onClick={submit}
          >
            {submitting ? 'Starting…' : 'Start run'}
          </SBButton>
        </div>
      </div>
    </div>
  );
}
