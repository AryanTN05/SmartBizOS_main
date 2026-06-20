import React from 'react';
import { SBIcon } from '../../../components/primitives';

// Visual step row used by Run detail + Template detail.
// Mirrors the UI kit's TimelineStep: status dot, kind label, optional ms/duration.
// `static` mode (no status) is used by Template detail — renders a muted node
// but keeps the same geometry so the two surfaces feel consistent.
export default function TimelineStep({ step, last, static: isStatic }) {
  const col = {
    done: 'var(--sb-accent)',
    active: 'var(--sb-warm)',
    pending: 'var(--sb-fg-5)',
    failed: 'var(--sb-hot)',
  }[step.status || 'pending'];

  const staticCol = 'var(--sb-fg-5)';
  const dotCol = isStatic ? staticCol : col;

  const kindLabel = {
    run: 'step.run',
    send: 'step.run',
    sleep: 'step.sleep',
    wait: 'step.sleep',
    wait_for_event: 'step.waitForEvent',
    check: 'step.run',
    branch: 'branch',
  }[step.kind] || 'step.run';

  return (
    <div style={{
      display: 'flex', gap: 14, padding: '14px 18px',
      borderBottom: last ? 'none' : '1px solid var(--sb-line)',
      position: 'relative',
    }}>
      <div style={{ width: 28, display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative' }}>
        <div style={{
          width: 20, height: 20, border: `1.5px solid ${dotCol}`,
          background: !isStatic && step.status === 'done' ? dotCol : 'transparent',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: !isStatic && step.status === 'active' ? `0 0 12px ${dotCol}` : 'none',
        }}>
          {!isStatic && step.status === 'done' && <SBIcon name="check" size={11} stroke={2.5} />}
          {!isStatic && step.status === 'active' && (
            <div style={{
              width: 6, height: 6, background: dotCol, borderRadius: '50%',
              animation: 'sb-pulse 1.5s infinite',
            }} />
          )}
          {isStatic && step.order != null && (
            <span style={{
              fontFamily: 'var(--sb-font-mono)', fontSize: 9, color: 'var(--sb-fg-4)', fontWeight: 700,
            }}>{step.order + 1}</span>
          )}
        </div>
        {!last && (
          <div style={{
            flex: 1, width: 1,
            background: !isStatic && step.status === 'done' ? 'var(--sb-accent-dim)' : 'var(--sb-line-2)',
            marginTop: 4,
          }} />
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0, paddingBottom: last ? 0 : 4 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <span style={{
            fontFamily: 'var(--sb-font-mono)', fontSize: 12.5, fontWeight: 600,
            color: !isStatic && step.status === 'pending' ? 'var(--sb-fg-5)' : 'var(--sb-fg)',
          }}>
            {step.name}
          </span>
          <span style={{
            fontFamily: 'var(--sb-font-mono)', fontSize: 10, color: 'var(--sb-fg-5)',
            textTransform: 'uppercase', letterSpacing: '0.12em',
          }}>{kindLabel}</span>
          {step.channel && (
            <span style={{
              fontFamily: 'var(--sb-font-mono)', fontSize: 10, color: 'var(--sb-fg-4)',
              textTransform: 'uppercase', letterSpacing: '0.1em',
            }}>· {step.channel}</span>
          )}
          <div style={{ flex: 1 }} />
          {step.ms != null && (
            <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 10.5, color: 'var(--sb-fg-5)' }}>{step.ms}ms</span>
          )}
          {step.duration && (
            <span style={{
              fontFamily: 'var(--sb-font-mono)', fontSize: 10.5,
              color: step.status === 'active' ? 'var(--sb-warm)' : 'var(--sb-fg-5)',
            }}>{step.duration}</span>
          )}
        </div>
        {(step.result || step.detail || step.description) && (
          <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', marginTop: 3 }}>
            {step.result || step.detail || step.description}
          </div>
        )}
      </div>
    </div>
  );
}
