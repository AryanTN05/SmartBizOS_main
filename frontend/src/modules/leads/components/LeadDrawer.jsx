import React, { useCallback, useEffect, useRef, useState } from 'react';
import { SBAvatar, SBButton, SBChip, SBIcon, SBSkeleton } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { useLaraUI } from '../../../lib/LaraUIContext.jsx';
import StartRunModal from '../../automations/components/StartRunModal.jsx';
import {
  scoreTone, tagTone, activityIcon, activityColor, relTime, scoreCategory,
  intentMeta, triggerMeta,
} from '../lib/helpers.js';
import { toast } from '../lib/toast.jsx';

// Lead detail drawer — ported from ui_kits/smartbiz/Leads.jsx.
// Score card (with corner brackets + rubric reasons), timeline, inline-editable
// fields, and action buttons (Start sequence, Email, Ask Lara).

const FIELD_STYLE = {
  background: 'var(--sb-panel)',
  border: '1px solid var(--sb-line)',
  color: 'var(--sb-fg)',
  fontSize: 13,
  fontFamily: 'var(--sb-font)',
  padding: '7px 10px',
  outline: 'none',
  width: '100%',
};

export default function LeadDrawer({ leadId, initialLead, onClose, onUpdate, onDelete }) {
  const { openDrawer: openLara } = useLaraUI();
  const [lead, setLead] = useState(initialLead || null);
  const [activity, setActivity] = useState([]);
  const [scoreHistory, setScoreHistory] = useState([]);
  const [enrichCtx, setEnrichCtx] = useState(null); // {source, enrichment} | null
  const [loading, setLoading] = useState(!initialLead);
  const [scoring, setScoring] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showStartRun, setShowStartRun] = useState(false);
  const [replyModal, setReplyModal] = useState(null); // {snippet} | null
  const [savingReply, setSavingReply] = useState(false);
  // Compose modal state — null when closed, {subject, body, mode} when open.
  // mode: 'cold' = first-touch send | 'reply' = AI-drafted response to a reply
  const [composeModal, setComposeModal] = useState(null);
  const [sendingCompose, setSendingCompose] = useState(false);
  const [editing, setEditing] = useState({}); // field name -> draft value
  const pollRef = useRef(null);

  // ---- fetch on mount / id change ---------------------------------------
  const fetchLead = useCallback(async () => {
    if (!leadId) return;
    setLoading(true);
    try {
      const res = await api.get(`/api/leads/${leadId}`);
      setLead(res.lead || res);
    } catch (err) {
      if (err.status === 404) {
        toast.error('Lead not found');
        onClose?.();
        return;
      }
      if (initialLead) {
        setLead(initialLead);
      } else {
        toast.error(err.message || 'Could not load lead.');
        onClose?.();
      }
    } finally {
      setLoading(false);
    }
  }, [leadId, initialLead, onClose]);

  const fetchActivity = useCallback(async () => {
    if (!leadId) return;
    try {
      const res = await api.get(`/api/leads/${leadId}/activity?limit=50`);
      setActivity(res.items || []);
    } catch (_err) {
      setActivity([]);
    }
  }, [leadId]);

  const fetchScoreHistory = useCallback(async () => {
    if (!leadId) return;
    try {
      const res = await api.get(`/api/leads/${leadId}/score/history?limit=20`);
      setScoreHistory(res.items || []);
    } catch (_err) {
      setScoreHistory([]);
    }
  }, [leadId]);

  // Drawer enrichment context — only set when the lead was promoted from a
  // scraper capture (source startsWith "scraper:"). 404 = not scraper-sourced,
  // which is expected and silent.
  const fetchEnrichCtx = useCallback(async () => {
    if (!leadId) return;
    try {
      const res = await api.get(`/api/leads/${leadId}/enrichment-context`);
      setEnrichCtx(res);
    } catch (_err) {
      setEnrichCtx(null);
    }
  }, [leadId]);

  useEffect(() => {
    fetchLead();
    fetchActivity();
    fetchScoreHistory();
    fetchEnrichCtx();
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [leadId, fetchLead, fetchActivity, fetchScoreHistory, fetchEnrichCtx]);

  // ---- inline edit -------------------------------------------------------
  const beginEdit = (k, v) => setEditing((e) => ({ ...e, [k]: v ?? '' }));
  const cancelEdit = (k) => setEditing((e) => {
    const n = { ...e }; delete n[k]; return n;
  });
  const commitEdit = async (k) => {
    const value = editing[k];
    if (value === lead[k]) { cancelEdit(k); return; }
    
    const parsedValue = k === 'tags'
      ? value.split(',').map((t) => t.trim()).filter(Boolean)
      : value;
      
    const apiField = k === 'company' ? 'company_name' : k;
    const body = { [apiField]: parsedValue };
    
    const prev = lead;
    setLead({ ...prev, [k]: parsedValue, [apiField]: parsedValue });
    cancelEdit(k);
    try {
      const res = await api.patch(`/api/leads/${leadId}`, body);
      setLead(res.lead || res);
      onUpdate?.(res.lead || res);
      toast.success('Saved');
    } catch (err) {
      setLead(prev);
      toast.error(err.message || 'Update failed');
    }
  };

  // ---- actions -----------------------------------------------------------
  const doRescore = async (chainIfNeeded = false) => {
    if (!lead) return;
    setScoring(true);
    try {
      const res = await api.post(`/api/leads/${leadId}/rescore`);
      const fresh = res.score || res;
      setLead((l) => ({ ...l, score: fresh }));
      toast.success(res.was_cached ? 'Score (cached)' : 'Score refreshed');
      onUpdate?.({ ...lead, score: fresh });
    } catch (err) {
      if (err.status === 409 && err.details?.reason === 'needs_enrichment_first') {
        if (chainIfNeeded) {
          toast.info('Enriching first…');
          await doEnrich({ chainRescore: true });
        } else {
          toast.error('No enrichment yet — click "Enrich & score".');
        }
      } else {
        toast.error(err.message || 'Score failed');
      }
    } finally {
      setScoring(false);
    }
  };

  const doEnrich = async ({ chainRescore = false } = {}) => {
    if (!lead) return;
    setEnriching(true);
    try {
      await api.post(`/api/leads/${leadId}/enrich`);
      toast.info('Enrichment queued…');
      // Poll activity up to ~30s looking for kind="enrichment". Capture the
      // lead id this poll is for, plus the timestamp baseline, so a fast
      // re-click on a different lead doesn't write enrichment results to the
      // wrong drawer state. Always clear any pre-existing interval before
      // starting a new one — guards against double-click leaks.
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      const pollLeadId = leadId;
      const since = lead.updated_at_unix || 0;
      let tries = 0;
      const tickFn = async () => {
        tries += 1;
        // Bail if the user navigated to a different lead mid-poll.
        if (pollLeadId !== leadId) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          return;
        }
        try {
          const res = await api.get(`/api/leads/${pollLeadId}/activity?limit=10&kind=enrichment`);
          if ((res.items || []).some((a) => a.occurred_at_unix > since)) {
            clearInterval(pollRef.current);
            pollRef.current = null;
            setEnriching(false);
            toast.success('Enrichment complete');
            await fetchActivity();
            await fetchLead();
            await fetchEnrichCtx();
            if (chainRescore) await doRescore(false);
            return;
          }
        } catch (_) { /* keep polling */ }
        if (tries > 15) { // ~30s
          clearInterval(pollRef.current);
          pollRef.current = null;
          setEnriching(false);
        }
      };
      pollRef.current = setInterval(tickFn, 2000);
    } catch (err) {
      setEnriching(false);
      toast.error(err.message || 'Enrich failed');
    }
  };

  const doDelete = async () => {
    try {
      await api.delete(`/api/leads/${leadId}`);
      toast.success('Lead deleted');
      onDelete?.(leadId);
      onClose?.();
    } catch (err) {
      toast.error(err.message || 'Delete failed');
    }
  };

  const doStartSequence = () => setShowStartRun(true);

  const openComposeCold = () => {
    if (!lead) return;
    const first = (lead.name || '').split(/\s+/)[0] || 'there';
    const company = lead.company || lead.company_name || 'your team';
    const opener = lead.opening_line ? `<p>${lead.opening_line}</p>` : '';
    const subject = `Quick idea for ${company}`;
    const body = (
      `<p>Hi ${first},</p>${opener}` +
      `<p>I work on SmartBiz OS — we help teams automate sales ops in ` +
      `week one. Worth a 15-min chat?</p><p>— SmartBiz OS</p>`
    );
    setComposeModal({ mode: 'cold', subject, body });
  };

  const openComposeReply = async () => {
    if (!lead) return;
    setComposeModal({ mode: 'reply', subject: `Re: your reply`,
                       body: '<p>Loading draft…</p>', drafting: true });
    try {
      const r = await api.post(`/api/leads/${leadId}/draft-reply`);
      setComposeModal({
        mode: 'reply', subject: r.subject || `Re: your reply`,
        body: r.body_html || '<p>(draft empty — write from scratch)</p>',
        drafting: false,
      });
    } catch (err) {
      toast.error(err?.message || 'Could not draft reply');
      setComposeModal(null);
    }
  };

  const submitCompose = async () => {
    if (!composeModal) return;
    setSendingCompose(true);
    try {
      const r = await api.post(`/api/leads/${leadId}/send-now`, {
        subject: composeModal.subject,
        body_html: composeModal.body,
      });
      toast.success(`Sent · ${r.mailbox_email || r.provider}`);
      setComposeModal(null);
      await fetchActivity();
      await fetchLead();
    } catch (err) {
      const code = err?.details?.code;
      if (code === 'suppressed') {
        toast.error(err?.details?.message || 'Recipient suppressed');
      } else {
        toast.error(err?.details?.message || err?.message || 'Send failed');
      }
    } finally {
      setSendingCompose(false);
    }
  };

  const submitReply = async () => {
    if (!replyModal) return;
    setSavingReply(true);
    try {
      await api.post(`/api/leads/${leadId}/reply`, {
        snippet: (replyModal.snippet || '').trim() || null,
        source: 'manual',
      });
      setLead((l) => ({ ...l, sequence_state: 'paused_replied' }));
      onUpdate?.({ ...lead, sequence_state: 'paused_replied' });
      await fetchActivity();
      setReplyModal(null);
      toast.success('Marked replied · sequence paused');
    } catch (err) {
      toast.error(err?.message || 'Could not mark replied');
    } finally {
      setSavingReply(false);
    }
  };

  if (!lead) {
    return (
      <>
        <div onClick={onClose} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 30,
        }} />
        <aside style={drawerStyle}>
          {loading ? (
            <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>
              {/* Header skeleton — avatar + name + close */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingBottom: 12, borderBottom: '1px solid var(--sb-line)' }}>
                <SBSkeleton variant="card" w={40} h={40} />
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <SBSkeleton variant="row" h={16} w={180} />
                  <SBSkeleton variant="row" h={12} w={120} style={{ opacity: 0.6 }} />
                </div>
              </div>
              {/* Score card skeleton */}
              <SBSkeleton variant="card" h={140} />
              {/* Field block skeleton */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {Array.from({ length: 4 }).map((_, i) => (
                  <SBSkeleton key={i} variant="row" h={20} style={{ opacity: Math.max(0.3, 1 - i * 0.15) }} />
                ))}
              </div>
            </div>
          ) : (
            <div style={{ padding: 36, color: 'var(--sb-fg-4)', fontFamily: 'var(--sb-font-mono)' }}>
              ▸ not found
            </div>
          )}
        </aside>
      </>
    );
  }

  const score = lead.score;
  const scoreVal = score?.value;
  const category = score?.category || scoreCategory(scoreVal);
  const tone = scoreTone(scoreVal);

  return (
    <>
      <div onClick={onClose} style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 30,
      }} />
      <aside style={drawerStyle}>
        {/* Header */}
        <div style={{
          padding: '18px 24px', borderBottom: '1px solid var(--sb-line)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <SBAvatar name={lead.name} color="var(--sb-violet)" size={40} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>{lead.name || '(unnamed)'}</div>
              {lead.sequence_state === 'paused_replied' && (() => {
                const m = intentMeta(lead.last_reply_intent);
                return m
                  ? <SBChip tone={m.tone} icon={m.icon}>replied · {m.label}</SBChip>
                  : <SBChip tone="hot" icon="check">replied</SBChip>;
              })()}
              {(lead.triggers || []).map((t) => {
                const m = triggerMeta(t);
                return <SBChip key={`trg-${t}`} tone={m.tone} icon={m.icon}>{m.label}</SBChip>;
              })}
            </div>
            <div style={{ fontSize: 12, color: 'var(--sb-fg-4)', fontFamily: 'var(--sb-font-mono)' }}>
              {lead.company || '—'}{lead._value ? ` · ${lead._value}` : ''}
            </div>
          </div>
          <button onClick={() => setConfirmDelete(true)} style={iconButtonStyle} title="Delete">
            <SBIcon name="close" size={14} />
          </button>
          <button onClick={onClose} style={iconButtonStyle} title="Close">
            <SBIcon name="chevronR" size={16} />
          </button>
        </div>

        <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 24 }}>
          {/* Score explainer card */}
          <div>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 10,
            }}>
              <span className="sb-label">Score · explained</span>
              <div style={{ display: 'flex', gap: 6 }}>
                {category && (
                  <SBChip tone={category === 'hot' ? 'hot' : category === 'warm' ? 'warm' : 'muted'} icon={category === 'hot' ? 'flame' : undefined}>
                    {category}
                  </SBChip>
                )}
              </div>
            </div>
            <div className="sb-brackets" style={{ padding: '18px 20px', background: 'var(--sb-card)' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14 }}>
                <div style={{
                  fontSize: 44, fontWeight: 500, letterSpacing: '-0.03em',
                  fontFamily: 'var(--sb-font-mono)', color: tone, lineHeight: 1,
                }}>{scoreVal != null ? scoreVal : '—'}</div>
                <div style={{ fontSize: 12, color: 'var(--sb-fg-4)', fontFamily: 'var(--sb-font-mono)' }}>
                  /100 · rubric {score?.rubric_version || 'v?'} · {score?.model || '—'}
                </div>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                  <SBButton variant="ghost" size="xs" icon="spark"
                    onClick={() => doRescore(true)} disabled={scoring}>
                    {scoring ? '…' : 'Re-score'}
                  </SBButton>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {(score?.reasons || []).map((r, i) => {
                  const text = typeof r === 'string' ? r : r.r || r.reason || JSON.stringify(r);
                  const w = typeof r === 'object' && r.w != null ? r.w : null;
                  return (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12.5 }}>
                      {w != null && (
                        <span style={{
                          fontFamily: 'var(--sb-font-mono)', fontSize: 11, fontWeight: 700,
                          color: w > 0 ? 'var(--sb-accent)' : 'var(--sb-hot)', minWidth: 34,
                        }}>{w > 0 ? '+' : ''}{w}</span>
                      )}
                      <span style={{ color: 'var(--sb-fg-2)', flex: 1 }}>{text}</span>
                    </div>
                  );
                })}
                {(!score || !(score.reasons || []).length) && (
                  <div style={{ fontSize: 12, color: 'var(--sb-fg-5)', fontStyle: 'italic' }}>
                    No reasons available — re-score to generate them.
                  </div>
                )}
              </div>

              {scoreHistory.length > 1 && (
                <ScoreSparkline history={scoreHistory} />
              )}
            </div>
          </div>

          {/* Scraper-source enrichment card — only when lead came from a scraper. */}
          {enrichCtx && <SourceCard ctx={enrichCtx} />}

          {/* AI-generated opening line — the wedge differentiator vs Apollo/Clay. */}
          <OpeningLineCard
            lead={lead}
            onChanged={(opener) => {
              setLead((l) => ({ ...l, opening_line: opener }));
              onUpdate?.({ ...lead, opening_line: opener });
            }}
          />

          {/* Inline-editable fields */}
          <div>
            <div className="sb-label" style={{ marginBottom: 10 }}>Details</div>
            <div style={{
              display: 'grid', gridTemplateColumns: '100px 1fr', gap: '8px 14px',
              fontSize: 12.5,
            }}>
              <Field label="name" value={lead.name} editing={editing.name}
                onBeginEdit={() => beginEdit('name', lead.name)}
                onChange={(v) => beginEdit('name', v)}
                onCancel={() => cancelEdit('name')}
                onCommit={() => commitEdit('name')} />
              <Field label="email" value={lead.email} editing={editing.email}
                onBeginEdit={() => beginEdit('email', lead.email)}
                onChange={(v) => beginEdit('email', v)}
                onCancel={() => cancelEdit('email')}
                onCommit={() => commitEdit('email')} />
              <Field label="phone" value={lead.phone} editing={editing.phone}
                onBeginEdit={() => beginEdit('phone', lead.phone)}
                onChange={(v) => beginEdit('phone', v)}
                onCancel={() => cancelEdit('phone')}
                onCommit={() => commitEdit('phone')} />
              <Field label="company" value={lead.company} editing={editing.company}
                onBeginEdit={() => beginEdit('company', lead.company)}
                onChange={(v) => beginEdit('company', v)}
                onCancel={() => cancelEdit('company')}
                onCommit={() => commitEdit('company')} />
              <Field label="title" value={lead.title} editing={editing.title}
                onBeginEdit={() => beginEdit('title', lead.title)}
                onChange={(v) => beginEdit('title', v)}
                onCancel={() => cancelEdit('title')}
                onCommit={() => commitEdit('title')} />
              <Field label="tags"
                value={(lead.tags || []).join(', ')}
                editing={editing.tags}
                placeholder="comma-separated"
                onBeginEdit={() => beginEdit('tags', (lead.tags || []).join(', '))}
                onChange={(v) => beginEdit('tags', v)}
                onCancel={() => cancelEdit('tags')}
                onCommit={() => commitEdit('tags')} />
            </div>
          </div>

          {/* Timeline */}
          <div>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10,
            }}>
              <span className="sb-label">Timeline</span>
              <SBButton variant="ghost" size="xs" icon="spark"
                onClick={() => doEnrich()} disabled={enriching}>
                {enriching ? 'Enriching…' : 'Re-enrich'}
              </SBButton>
            </div>
            <NoteInput
              leadId={leadId}
              onAdded={(act) => {
                setActivity((a) => [act, ...a]);
              }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0, marginTop: 12 }}>
              {activity.length === 0 && (
                <div style={{ fontSize: 12, color: 'var(--sb-fg-5)', fontStyle: 'italic' }}>
                  No activity yet.
                </div>
              )}
              {activity.map((a) => (
                <div key={a.id} style={{
                  display: 'flex', gap: 12, padding: '10px 0',
                  borderBottom: '1px solid var(--sb-line)',
                }}>
                  <div style={{
                    width: 24, height: 24, background: 'var(--sb-card)',
                    border: '1px solid var(--sb-line-2)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: activityColor(a.kind), flexShrink: 0,
                  }}>
                    <SBIcon name={activityIcon(a.kind)} size={11} stroke={1.5} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, color: 'var(--sb-fg)', fontWeight: 600 }}>
                      {labelForKind(a.kind)}
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', marginTop: 2 }}>
                      {summarizePayload(a)}
                    </div>
                  </div>
                  <div style={{
                    fontSize: 10.5, color: 'var(--sb-fg-5)',
                    fontFamily: 'var(--sb-font-mono)',
                  }}>{relTime(a.occurred_at_unix)}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <SBButton variant="primary" icon="mail"
              onClick={openComposeCold}
              disabled={!lead.email}>
              Compose & send
            </SBButton>
            {lead.last_reply_intent === 'positive' && (
              <SBButton variant="primary" icon="spark" onClick={openComposeReply}>
                Draft reply
              </SBButton>
            )}
            <SBButton variant="secondary" icon="bolt" onClick={doStartSequence}>
              Start sequence
            </SBButton>
            {lead.sequence_state === 'paused_replied' ? (
              <SBButton variant="ghost" icon="spark"
                onClick={async () => {
                  try {
                    await api.post(`/api/leads/${leadId}/resume-sequence`);
                    setLead((l) => ({ ...l, sequence_state: 'active' }));
                    onUpdate?.({ ...lead, sequence_state: 'active' });
                    toast.success('Sequence resumed');
                  } catch (err) {
                    toast.error(err?.message || 'Could not resume');
                  }
                }}>
                Resume sequence
              </SBButton>
            ) : (
              <SBButton variant="ghost" icon="check"
                onClick={() => setReplyModal({ snippet: '' })}>
                Mark replied
              </SBButton>
            )}
            <SBButton variant="ghost" icon="lara"
              onClick={() => openLara({ lead })}>
              Ask Lara
            </SBButton>
          </div>
        </div>

        {confirmDelete && (
          <div style={{
            position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10,
          }}>
            <div style={{
              background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-2)',
              padding: 24, width: 360, maxWidth: '90%',
            }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>
                Delete this lead?
              </div>
              <div style={{ fontSize: 12.5, color: 'var(--sb-fg-4)', marginBottom: 16 }}>
                Soft delete — row is tombstoned, activity retained for audit.
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <SBButton variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</SBButton>
                <SBButton variant="danger" icon="close" onClick={doDelete}>Delete</SBButton>
              </div>
            </div>
          </div>
        )}

        {composeModal && (
          <div style={{
            position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10,
          }}>
            <div style={{
              background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-2)',
              padding: 24, width: 540, maxWidth: '94%',
              display: 'flex', flexDirection: 'column', gap: 12,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ fontSize: 14, fontWeight: 600, flex: 1 }}>
                  {composeModal.mode === 'reply' ? 'Draft reply to ' : 'Send to '}
                  <span style={{ fontFamily: 'var(--sb-font-mono)', color: 'var(--sb-fg-3)' }}>
                    {lead.email}
                  </span>
                </div>
                {composeModal.mode === 'reply' && (
                  <SBChip tone="lime" icon="spark">AI-drafted</SBChip>
                )}
              </div>
              <div style={{ fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
                Routed via your mailbox rotation (or Resend fallback). Includes
                a one-click unsubscribe footer + List-Unsubscribe header.
              </div>

              <div>
                <div style={{
                  fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
                  textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4,
                }}>Subject</div>
                <input
                  value={composeModal.subject}
                  onChange={(e) => setComposeModal({ ...composeModal, subject: e.target.value })}
                  disabled={composeModal.drafting}
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    background: 'var(--sb-panel)', color: 'var(--sb-fg)',
                    border: '1px solid var(--sb-line-2)', padding: '8px 12px',
                    fontSize: 13, fontFamily: 'var(--sb-font)', outline: 'none',
                  }}
                />
              </div>

              <div>
                <div style={{
                  fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
                  textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4,
                }}>Body (HTML)</div>
                <textarea
                  value={composeModal.body}
                  onChange={(e) => setComposeModal({ ...composeModal, body: e.target.value })}
                  disabled={composeModal.drafting}
                  rows={12}
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    background: 'var(--sb-panel)', color: 'var(--sb-fg)',
                    border: '1px solid var(--sb-line-2)', padding: '10px 12px',
                    fontSize: 12.5, fontFamily: 'var(--sb-font-mono)', lineHeight: 1.55,
                    resize: 'vertical', outline: 'none',
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <SBButton variant="ghost" onClick={() => setComposeModal(null)}
                  disabled={sendingCompose}>
                  Cancel
                </SBButton>
                <SBButton variant="primary" icon="bolt"
                  disabled={sendingCompose || composeModal.drafting || !composeModal.subject || !composeModal.body}
                  onClick={submitCompose}>
                  {sendingCompose ? 'Sending…' : composeModal.drafting ? 'Drafting…' : 'Send'}
                </SBButton>
              </div>
            </div>
          </div>
        )}

        {replyModal && (
          <div style={{
            position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10,
          }}>
            <div style={{
              background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-2)',
              padding: 24, width: 420, maxWidth: '92%',
            }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>
                Mark as replied
              </div>
              <div style={{ fontSize: 12.5, color: 'var(--sb-fg-4)', marginBottom: 12, lineHeight: 1.55 }}>
                Pauses any active sequence so they don't get more outbound. Snippet is optional — useful for skimming the timeline later.
              </div>
              <textarea
                autoFocus
                value={replyModal.snippet}
                onChange={(e) => setReplyModal({ snippet: e.target.value })}
                placeholder="Paste their reply, or leave blank…"
                rows={4}
                maxLength={1000}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    submitReply();
                  } else if (e.key === 'Escape') {
                    setReplyModal(null);
                  }
                }}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: 'var(--sb-panel)', color: 'var(--sb-fg)',
                  border: '1px solid var(--sb-line-2)', padding: '10px 12px',
                  fontSize: 13, fontFamily: 'var(--sb-font)', lineHeight: 1.55,
                  resize: 'vertical', outline: 'none',
                }}
              />
              <div style={{
                marginTop: 4, marginBottom: 12, fontSize: 10.5, color: 'var(--sb-fg-5)',
                fontFamily: 'var(--sb-font-mono)', display: 'flex', justifyContent: 'space-between',
              }}>
                <span>⌘/Ctrl + Enter to confirm · Esc to cancel</span>
                <span>{(replyModal.snippet || '').length} / 1000</span>
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <SBButton variant="ghost" onClick={() => setReplyModal(null)} disabled={savingReply}>
                  Cancel
                </SBButton>
                <SBButton variant="primary" icon="check" onClick={submitReply} disabled={savingReply}>
                  {savingReply ? 'Saving…' : 'Mark replied'}
                </SBButton>
              </div>
            </div>
          </div>
        )}
      </aside>
      <StartRunModal
        open={showStartRun}
        onClose={() => setShowStartRun(false)}
        leadId={leadId}
        onRunCreated={() => {
          setShowStartRun(false);
          toast.success('Sequence started');
          fetchActivity();
        }}
      />
      <style>{`
        @keyframes sb-slide-in {
          from { transform: translateX(24px); opacity: 0.6; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </>
  );
}

const drawerStyle = {
  position: 'fixed', top: 0, right: 0, bottom: 0,
  width: 540, maxWidth: '92vw',
  background: 'var(--sb-bg)', borderLeft: '1px solid var(--sb-line-2)',
  overflow: 'auto', zIndex: 35,
  animation: 'sb-slide-in 240ms cubic-bezier(.2,.8,.2,1) forwards',
};

const iconButtonStyle = {
  background: 'transparent', border: 'none',
  color: 'var(--sb-fg-4)', cursor: 'pointer',
  padding: 4, display: 'inline-flex', alignItems: 'center',
};

function labelForKind(kind) {
  const map = {
    email: 'Email', note: 'Note', status_change: 'Stage changed',
    enrichment: 'Enriched', automation_event: 'Automation',
    score_changed: 'Score changed', mcp_sync: 'Synced',
    reply_received: 'Replied',
  };
  return map[kind] || kind;
}

function summarizePayload(a) {
  const p = a.payload || {};
  if (a.kind === 'email') return p.subject || 'outbound';
  if (a.kind === 'status_change') return `${p.from || '?'} → ${p.to || '?'}`;
  if (a.kind === 'enrichment') return `providers: ${(p.providers || []).join(', ') || '—'}`;
  if (a.kind === 'automation_event') return p.template || p.template_id || 'run';
  if (a.kind === 'score_changed') return `${p.old ?? '?'} → ${p.new ?? '?'}`;
  if (a.kind === 'mcp_sync') return p.source || p.provider || 'sync';
  if (a.kind === 'note') return p.text || 'note';
  if (a.kind === 'reply_received') {
    const src = p.source ? ` · via ${p.source}` : '';
    const snip = (p.snippet || '').trim();
    if (snip) return `${snip.slice(0, 140)}${snip.length > 140 ? '…' : ''}${src}`;
    return `(no snippet)${src}`;
  }
  return '';
}

function Field({ label, value, editing, onBeginEdit, onChange, onCancel, onCommit, placeholder }) {
  return (
    <>
      <div style={{
        color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
        fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.1em',
        paddingTop: 7,
      }}>{label}</div>
      <div>
        {editing !== undefined ? (
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              value={editing}
              autoFocus
              placeholder={placeholder}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onCommit();
                if (e.key === 'Escape') onCancel();
              }}
              style={FIELD_STYLE}
            />
            <button onClick={onCommit} style={iconButtonStyle} title="Save">
              <SBIcon name="check" size={14} />
            </button>
            <button onClick={onCancel} style={iconButtonStyle} title="Cancel">
              <SBIcon name="close" size={14} />
            </button>
          </div>
        ) : (
          <div
            onClick={onBeginEdit}
            style={{
              fontSize: 12.5, color: value ? 'var(--sb-fg-2)' : 'var(--sb-fg-5)',
              cursor: 'pointer', padding: '7px 10px',
              border: '1px solid transparent',
            }}
            onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--sb-line)'}
            onMouseLeave={(e) => e.currentTarget.style.borderColor = 'transparent'}
          >
            {value || <span style={{ fontStyle: 'italic' }}>(empty — click to edit)</span>}
          </div>
        )}
      </div>
    </>
  );
}

// Tiny inline form to add a manual note to a lead's activity timeline.
// SDR workflow: "called, no answer, ringback Tuesday" — kept to one line so
// it doesn't dominate the drawer; press Enter to submit.
function NoteInput({ leadId, onAdded }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    try {
      const r = await api.post(`/api/leads/${leadId}/notes`, { text: t });
      onAdded?.(r);
      setText('');
    } catch (err) {
      toast.error(err?.message || 'Could not add note');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
        placeholder="Add a note — Enter to save"
        disabled={busy}
        style={{
          flex: 1, padding: '7px 10px',
          background: 'var(--sb-panel)', color: 'var(--sb-fg)',
          border: '1px solid var(--sb-line-2)', fontSize: 12.5,
          fontFamily: 'var(--sb-font)', outline: 'none',
        }}
      />
      <SBButton variant="ghost" size="xs" icon="plus" disabled={busy || !text.trim()} onClick={submit}>
        {busy ? '…' : 'Note'}
      </SBButton>
    </div>
  );
}

// AI-drafted personalized opener grounded in the lead's source signal.
// Per the May 2026 competitive scan, generic merge-tag personalization gets
// 0.5-1.5% reply rates because both spam filters and humans recognize it
// instantly. The wedge: ground ONE sentence in a real, fresh signal that the
// prospect actually shipped (PH launch, YC batch, GitHub repo, HN post).
function OpeningLineCard({ lead, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(lead?.opening_line || '');
  const [showVariants, setShowVariants] = useState(false);
  const [variants, setVariants] = useState(lead?.opening_line_variants || []);
  const opener = lead?.opening_line;

  // Keep local variants in sync when the lead prop updates (after parent
  // refetch).
  React.useEffect(() => {
    setVariants(lead?.opening_line_variants || []);
  }, [lead?.id, lead?.opening_line_variants]);

  const generate = async ({ force = false } = {}) => {
    setBusy(true);
    try {
      const r = await api.post(`/api/leads/${lead.id}/opening-line/generate`, { force });
      onChanged?.(r.opening_line);
      toast.success(force ? 'Regenerated opener' : 'Opener generated');
    } catch (err) {
      const msg = err?.details?.message || err?.message || 'Generate failed';
      if (err?.details?.code === 'no_signal') {
        toast.info('No source signal yet — add notes or trigger enrichment first.');
      } else {
        toast.error(msg);
      }
    } finally {
      setBusy(false);
    }
  };

  const generateVariants = async ({ force = false } = {}) => {
    setBusy(true);
    try {
      const r = await api.post(`/api/leads/${lead.id}/opening-line/variants`, { count: 3, force });
      setVariants(r.variants || []);
      onChanged?.(r.active);
      setShowVariants(true);
      toast.success(`${(r.variants || []).length} variants drafted`);
    } catch (err) {
      const msg = err?.details?.message || err?.message || 'Variants failed';
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const promote = async (idx) => {
    try {
      const r = await api.post(`/api/leads/${lead.id}/opening-line/promote`, { index: idx });
      onChanged?.(r.opening_line);
      toast.success('Active variant updated');
    } catch (err) {
      toast.error(err?.message || 'Promote failed');
    }
  };

  const saveEdit = async () => {
    setBusy(true);
    try {
      const r = await api.patch(`/api/leads/${lead.id}/opening-line`, {
        opening_line: draft.trim() || null,
      });
      onChanged?.(r.opening_line);
      setEditing(false);
      toast.success('Saved');
    } catch (err) {
      toast.error(err?.message || 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 10,
      }}>
        <span className="sb-label">
          Opening line · AI
          {variants.length > 0 && (
            <span style={{ marginLeft: 8, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', fontSize: 10 }}>
              {variants.length} variants
            </span>
          )}
        </span>
        <div style={{ display: 'flex', gap: 6 }}>
          {variants.length > 0 && !editing && (
            <SBButton variant="ghost" size="xs" icon="leads"
              onClick={() => setShowVariants((v) => !v)}>
              {showVariants ? 'Hide' : 'A/B'}
            </SBButton>
          )}
          {opener && !editing && (
            <SBButton variant="ghost" size="xs" icon="edit"
              onClick={() => { setDraft(opener); setEditing(true); }}>
              Edit
            </SBButton>
          )}
          {opener && !editing && (
            <SBButton variant="ghost" size="xs" icon="spark"
              disabled={busy} onClick={() => generateVariants({ force: true })}>
              {variants.length > 0 ? 'Re-A/B' : 'Make A/B'}
            </SBButton>
          )}
        </div>
      </div>
      <div style={{
        background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
        padding: '14px 16px',
      }}>
        {editing ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={3}
              maxLength={600}
              style={{
                width: '100%', boxSizing: 'border-box',
                background: 'var(--sb-panel)', color: 'var(--sb-fg)',
                border: '1px solid var(--sb-line-2)', padding: '10px 12px',
                fontSize: 13, fontFamily: 'var(--sb-font)', lineHeight: 1.55,
                resize: 'vertical', outline: 'none',
              }}
            />
            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
              <SBButton variant="ghost" size="xs" onClick={() => setEditing(false)}>Cancel</SBButton>
              <SBButton variant="primary" size="xs" icon="check" disabled={busy} onClick={saveEdit}>
                {busy ? 'Saving…' : 'Save'}
              </SBButton>
            </div>
          </div>
        ) : opener ? (
          <>
            <div style={{
              fontSize: 13.5, color: 'var(--sb-fg)', lineHeight: 1.6,
              fontStyle: 'italic',
            }}>
              “{opener}”
            </div>
            {showVariants && variants.length > 0 && (
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--sb-line)',
                            display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
                              textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  variants — scheduler picks winner once each has 3+ sends
                </div>
                {variants.map((v, i) => {
                  const sent = v.sent_count || 0;
                  const replied = v.replied_count || 0;
                  const rate = sent > 0 ? (replied / sent) : 0;
                  const active = v.text === opener;
                  return (
                    <div key={i} style={{
                      padding: '8px 10px',
                      background: active ? 'var(--sb-accent-bg)' : 'var(--sb-panel)',
                      border: `1px solid ${active ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
                    }}>
                      <div style={{
                        fontSize: 12, color: 'var(--sb-fg-2)', lineHeight: 1.5,
                        fontStyle: 'italic',
                      }}>
                        {v.text}
                      </div>
                      <div style={{
                        marginTop: 4, fontSize: 10, color: 'var(--sb-fg-5)',
                        fontFamily: 'var(--sb-font-mono)',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      }}>
                        <span>
                          sent {sent} · replied {replied}
                          {sent > 0 && (
                            <> · <span style={{ color: 'var(--sb-accent)' }}>{(rate * 100).toFixed(0)}%</span></>
                          )}
                        </span>
                        {!active && (
                          <button onClick={() => promote(i)}
                            style={{
                              background: 'transparent', border: 'none',
                              color: 'var(--sb-accent)', cursor: 'pointer',
                              fontFamily: 'var(--sb-font-mono)', fontSize: 10,
                              textTransform: 'uppercase', letterSpacing: '0.08em',
                            }}>use this</button>
                        )}
                        {active && <span style={{ color: 'var(--sb-accent)' }}>active</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontSize: 12, color: 'var(--sb-fg-4)', lineHeight: 1.55 }}>
              Generate one personalized sentence grounded in this lead's source
              signal — works best with scraper-sourced leads (Product Hunt
              launch, YC batch, GitHub repo, HN post).
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <SBButton variant="primary" size="xs" icon="spark"
                disabled={busy} onClick={() => generate()}>
                {busy ? 'Drafting…' : 'Generate opener'}
              </SBButton>
              <SBButton variant="ghost" size="xs" icon="leads"
                disabled={busy} onClick={() => generateVariants()}>
                Generate 3 A/B
              </SBButton>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Renders the scraper-origin context for a lead — source URL, page snippet,
// detected tech, Hunter intel, email-verification result. Only mounted when
// the enrichment-context endpoint returned a body (i.e. lead.source startsWith
// "scraper:"). Designed to give the SDR everything they'd otherwise have to
// dig out of `notes` or click into the scraper-results page for.
function SourceCard({ ctx }) {
  const src = ctx.source || {};
  const e = ctx.enrichment || {};
  const hunter = e.hunter || {};
  const verify = e.email_verification || {};
  const sourceLabel = (src.type || 'unknown').replace(/_/g, ' ');

  return (
    <div>
      <div className="sb-label" style={{ marginBottom: 10 }}>Source</div>
      <div style={{
        background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
        padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12,
      }}>
        {/* origin row: type + URL */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <SBChip tone="muted" icon="eye">{sourceLabel}</SBChip>
          {src.url && (
            <a
              href={src.url} target="_blank" rel="noopener noreferrer"
              style={{
                fontSize: 11.5, color: 'var(--sb-accent)',
                fontFamily: 'var(--sb-font-mono)', textDecoration: 'none',
                wordBreak: 'break-all', flex: 1, minWidth: 0,
              }}
            >{src.url}</a>
          )}
          {src.relevance_score != null && (
            <span style={{
              fontFamily: 'var(--sb-font-mono)', fontSize: 11,
              color: 'var(--sb-fg-5)',
            }}>capture-score · {src.relevance_score}</span>
          )}
        </div>

        {/* page snippet */}
        {(e.description || src.summary) && (
          <div style={{
            fontSize: 12.5, color: 'var(--sb-fg-2)', lineHeight: 1.55,
            paddingTop: 8, borderTop: '1px solid var(--sb-line)',
          }}>
            {e.description || src.summary}
          </div>
        )}

        {/* tech badges */}
        {(e.tech || []).length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {e.tech.slice(0, 12).map((t) => (
              <SBChip key={t} tone="cool">{t}</SBChip>
            ))}
          </div>
        )}

        {/* Hunter intel */}
        {(hunter.organization || hunter.industry || hunter.headcount) && (
          <div style={{
            display: 'grid', gridTemplateColumns: '110px 1fr', gap: '4px 12px',
            fontSize: 12, paddingTop: 8, borderTop: '1px solid var(--sb-line)',
          }}>
            <span style={{ color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', fontSize: 11 }}>company</span>
            <span style={{ color: 'var(--sb-fg-2)' }}>
              {hunter.organization || '—'}
              {hunter.country ? ` · ${hunter.country}` : ''}
            </span>
            {hunter.industry && (<>
              <span style={{ color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', fontSize: 11 }}>industry</span>
              <span style={{ color: 'var(--sb-fg-2)' }}>{hunter.industry}</span>
            </>)}
            {hunter.headcount && (<>
              <span style={{ color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', fontSize: 11 }}>headcount</span>
              <span style={{ color: 'var(--sb-fg-2)' }}>{hunter.headcount}</span>
            </>)}
          </div>
        )}

        {/* email verification */}
        {verify.result && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            paddingTop: 8, borderTop: '1px solid var(--sb-line)',
          }}>
            <span style={{ color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', fontSize: 11 }}>email</span>
            <SBChip tone={verify.result === 'deliverable' ? 'hot' : verify.result === 'risky' ? 'warm' : 'muted'}>
              {verify.result}
            </SBChip>
            {verify.score != null && (
              <span style={{ fontSize: 11.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
                · score {verify.score}
              </span>
            )}
          </div>
        )}

        {/* fetcher trace */}
        {e.fetcher && (
          <div style={{
            fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
            letterSpacing: '0.04em',
          }}>
            ▸ fetched via {e.fetcher}
            {src.scraped_at_unix ? ` · captured ${relTime(src.scraped_at_unix)}` : ''}
          </div>
        )}
      </div>
    </div>
  );
}

// Tiny inline sparkline + per-point reasons for the score-explainer card.
// `history` is server-shape: newest-first array of {score, reason, scored_at}.
function ScoreSparkline({ history }) {
  const ordered = history.slice().reverse(); // oldest → newest
  const min = Math.min(...ordered.map((p) => p.score));
  const max = Math.max(...ordered.map((p) => p.score));
  const range = Math.max(max - min, 1);
  const W = 220;
  const H = 36;
  const stepX = ordered.length > 1 ? W / (ordered.length - 1) : 0;
  const points = ordered.map((p, i) => {
    const x = i * stepX;
    const y = H - ((p.score - min) / range) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const latest = ordered[ordered.length - 1];
  const earliest = ordered[0];
  const delta = latest.score - earliest.score;
  return (
    <div style={{
      marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--sb-line)',
      display: 'flex', alignItems: 'center', gap: 14,
    }}>
      <svg width={W} height={H} style={{ display: 'block', flexShrink: 0 }}>
        <polyline
          points={points}
          fill="none"
          stroke="var(--sb-accent)"
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {ordered.map((p, i) => (
          <circle
            key={p.id || i}
            cx={i * stepX}
            cy={H - ((p.score - min) / range) * H}
            r="2"
            fill={i === ordered.length - 1 ? 'var(--sb-accent)' : 'var(--sb-fg-5)'}
          />
        ))}
      </svg>
      <div style={{ fontSize: 11.5, fontFamily: 'var(--sb-font-mono)', color: 'var(--sb-fg-4)' }}>
        <div>
          <span style={{ color: 'var(--sb-fg-5)' }}>{ordered.length}</span> rescores
          <span style={{ marginLeft: 10, color: delta > 0 ? 'var(--sb-accent)' : delta < 0 ? 'var(--sb-hot)' : 'var(--sb-fg-5)' }}>
            {delta > 0 ? '+' : ''}{delta}
          </span>
        </div>
        <div style={{ color: 'var(--sb-fg-5)', marginTop: 2 }}>
          {earliest.score} → {latest.score}
        </div>
      </div>
    </div>
  );
}
