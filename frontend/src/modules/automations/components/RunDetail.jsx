import React, { useState } from 'react';
import { SBButton, SBChip, SBStat, SBIcon } from '../../../components/primitives';
import { useLaraUI } from '../../../lib/LaraUIContext.jsx';
import TimelineStep from './TimelineStep.jsx';
import { timeAgo, formatElapsed, shortId, eventToTimelineStep } from '../lib/format.js';

// Right-pane detail for a selected run.
// Header + stat strip + timeline + actions.
// The caller owns the data fetch + refresh loop; this is a pure render.
export default function RunDetail({ detail, onPause, onCancel, actionState }) {
  const { openDrawer } = useLaraUI();
  const [confirmCancel, setConfirmCancel] = useState(false);

  if (!detail) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100%', color: 'var(--sb-fg-5)',
        fontFamily: 'var(--sb-font-mono)', fontSize: 12, letterSpacing: '0.12em',
        textTransform: 'uppercase',
      }}>
        ▸ select a run
      </div>
    );
  }

  const { run, events = [], lead, template } = detail;
  const status = run.status || 'running';
  const toneForStatus = {
    running: 'accent',
    paused: 'warm',
    completed: 'lime',
    failed: 'hot',
    cancelled: 'muted',
  }[status] || 'neutral';

  // Sort events by occurred_at_unix ASC per contract (late webhooks append).
  const sortedEvents = [...events].sort((a, b) => (a.occurred_at_unix || 0) - (b.occurred_at_unix || 0));

  // Project events onto TimelineStep shape, then append any pending steps
  // derived from the template so the viewer can see what's coming.
  const doneSteps = sortedEvents.map((ev, i) => eventToTimelineStep(ev, i, sortedEvents.length));
  // Mark the last non-failed step active if run is still running and the
  // backend hasn't sent a dedicated wait event.
  if (status === 'running' && doneSteps.length > 0) {
    const last = doneSteps[doneSteps.length - 1];
    if (last.status === 'done' && (run.current_step_name || '').startsWith('wait_')) {
      doneSteps.push({
        name: run.current_step_name,
        kind: 'wait_for_event',
        status: 'active',
        duration: run.next_fire_at_unix
          ? `fires ${timeAgo(run.next_fire_at_unix).replace(' ago', '')} from now`
          : null,
        detail: 'waiting for next event',
      });
    }
  }

  const totalSteps = template?.step_count || run._total || doneSteps.length || 1;
  const stepProgress = run._step != null
    ? `${run._step}/${totalSteps}`
    : `${Math.min(doneSteps.filter((s) => s.status === 'done').length, totalSteps)}/${totalSteps}`;

  const actionInFlight = actionState?.inflight;
  const actionError = actionState?.error;

  const leadLabel = lead
    ? `${lead.first_name || ''} ${lead.last_name || ''}`.trim() || lead.email
    : run._lead_display || shortId(run.lead_id);

  return (
    <div style={{ overflow: 'auto', padding: 28 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6, flexWrap: 'wrap' }}>
        <span className="sb-label" style={{ color: 'var(--sb-accent)', fontFamily: 'var(--sb-font-mono)' }}>
          {run.id}
        </span>
        <SBChip tone={toneForStatus} icon="dot">{status}</SBChip>
        {run.inngest_run_id && (
          <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 10.5, color: 'var(--sb-fg-5)' }}>
            · inngest {shortId(run.inngest_run_id)}
          </span>
        )}
        <div style={{ flex: 1 }} />
        {/* Actions */}
        {status === 'running' && (
          <SBButton
            variant="secondary"
            size="sm"
            icon="clock"
            disabled={actionInFlight === 'pause'}
            onClick={onPause}
          >
            {actionInFlight === 'pause' ? 'Pausing…' : 'Pause'}
          </SBButton>
        )}
        {(status === 'running' || status === 'paused') && (
          <SBButton
            variant="danger"
            size="sm"
            icon="close"
            disabled={actionInFlight === 'cancel'}
            onClick={() => setConfirmCancel(true)}
          >
            {actionInFlight === 'cancel' ? 'Cancelling…' : 'Cancel'}
          </SBButton>
        )}
        <SBButton
          variant="ghost"
          size="sm"
          icon="lara"
          onClick={() => openDrawer({
            prompt: `Show me Inngest diagnostics for run ${run.id}`,
            context: { kind: 'automation_run', run_id: run.id, inngest_run_id: run.inngest_run_id },
          })}
        >
          Raw Inngest state
        </SBButton>
      </div>

      <h2 style={{
        fontFamily: 'var(--sb-font-display)', fontSize: 24, fontWeight: 600,
        margin: '0 0 4px', letterSpacing: '-0.02em',
      }}>
        {template?.name || template?.key || run.template_key}
        {' '}<span style={{ color: 'var(--sb-fg-5)' }}>·</span>{' '}
        <span style={{ color: 'var(--sb-fg-3)' }}>{leadLabel}</span>
      </h2>
      <p style={{
        fontSize: 13, color: 'var(--sb-fg-4)', margin: '0 0 24px',
        fontFamily: 'var(--sb-font-mono)',
      }}>
        inngest_run · fn_id: nurture.{template?.key || run.template_key || 'unknown'} · started {timeAgo(run.started_at_unix)}
      </p>

      {actionError && (
        <div style={{
          padding: '10px 12px', background: 'rgba(255,90,106,0.08)',
          border: '1px solid var(--sb-hot)', fontSize: 12, color: 'var(--sb-fg-2)',
          marginBottom: 20,
        }}>
          <span style={{ color: 'var(--sb-hot)', fontFamily: 'var(--sb-font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            {actionError.code}
          </span>
          <span style={{ marginLeft: 8 }}>{actionError.message}</span>
        </div>
      )}

      {/* Stat strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 28 }}>
        <SBStat label="Step" value={stepProgress} mono />
        <SBStat label="Elapsed" value={formatElapsed(run.started_at_unix, run.completed_at_unix)} mono />
        <SBStat label="Events" value={String(sortedEvents.length)} mono />
        <SBStat label="Cost" value={`$${(0.0005 + sortedEvents.length * 0.0004).toFixed(3)}`} mono />
      </div>

      {/* Timeline */}
      <div className="sb-label" style={{ marginBottom: 12 }}>Timeline</div>
      <div style={{ background: 'var(--sb-card)', border: '1px solid var(--sb-line)' }}>
        {doneSteps.length === 0 ? (
          <div style={{
            padding: '18px 20px', color: 'var(--sb-fg-5)',
            fontFamily: 'var(--sb-font-mono)', fontSize: 12,
          }}>
            no events yet — run just enqueued
          </div>
        ) : (
          doneSteps.map((s, i) => (
            <TimelineStep key={i} step={s} last={i === doneSteps.length - 1} />
          ))
        )}
      </div>

      {/* Cancel confirm */}
      {confirmCancel && (
        <div
          onMouseDown={(e) => { if (e.target === e.currentTarget) setConfirmCancel(false); }}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60,
          }}
        >
          <div style={{
            width: 420, maxWidth: '92vw', background: 'var(--sb-card-2)',
            border: '1px solid var(--sb-line-2)', padding: 22,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <SBIcon name="warn" size={16} stroke={1.8} />
              <span className="sb-label" style={{ color: 'var(--sb-hot)' }}>Cancel run</span>
            </div>
            <p style={{ fontSize: 13, color: 'var(--sb-fg-2)', lineHeight: 1.55, margin: 0 }}>
              Cancelling is terminal — Inngest stops the function and the timeline is frozen.
              Any late webhook events (like opens) still append, but the run won't advance.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 18 }}>
              <SBButton variant="ghost" size="sm" onClick={() => setConfirmCancel(false)}>Keep running</SBButton>
              <SBButton
                variant="danger"
                size="sm"
                icon="close"
                onClick={() => { setConfirmCancel(false); onCancel?.(); }}
              >
                Cancel run
              </SBButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
