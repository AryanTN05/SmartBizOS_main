import React, { useCallback, useEffect, useState } from 'react';
import { SBButton, SBChip } from '../../../components/primitives';
import api from '../../../lib/api.js';
import EmptyState from '../components/EmptyState.jsx';

const KINDS = ['all', 'fact', 'doc_chunk', 'conversation_summary'];

// Admin memory browser. Lists extracted facts / doc chunks / summaries so a
// human can prune hallucinations or stale info.
export default function MemoryPage() {
  const [state, setState] = useState({ status: 'loading', items: [] });
  const [kind, setKind] = useState('all');

  const load = useCallback(async (k) => {
    setState({ status: 'loading', items: [] });
    try {
      const qs = new URLSearchParams({ limit: '50' });
      if (k && k !== 'all') qs.set('kind', k);
      const r = await api.get(`/api/admin/memory?${qs.toString()}`);
      setState({ status: 'ok', items: r?.items || [] });
    } catch (_) {
      setState({ status: 'empty', items: [] });
    }
  }, []);

  useEffect(() => { load(kind); }, [load, kind]);

  const onDelete = async (id) => {
    if (!window.confirm('Delete this memory entry? Hard delete — cannot undo.')) return;
    try { await api.delete(`/api/admin/memory/${id}`); } catch (_) { /* no-op */ }
    setState((s) => ({ ...s, items: s.items.filter((m) => m.id !== id) }));
  };

  return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{ marginBottom: 20 }}>
        <div className="sb-label">M1 · Lara</div>
        <h1 style={{
          fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 500,
          margin: '6px 0 0', letterSpacing: '-0.02em',
        }}>Memory</h1>
        <p style={{ color: 'var(--sb-fg-3)', fontSize: 13, marginTop: 6 }}>
          Long-term facts extracted from conversations and documents. Delete anything that looks wrong.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
        {KINDS.map((k) => (
          <button
            key={k}
            onClick={() => setKind(k)}
            style={{
              background: kind === k ? 'var(--sb-accent-bg)' : 'transparent',
              border: `1px solid ${kind === k ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
              color: kind === k ? 'var(--sb-accent)' : 'var(--sb-fg-3)',
              padding: '4px 10px', cursor: 'pointer',
              fontFamily: 'var(--sb-font-mono)', fontSize: 11,
              textTransform: 'uppercase', letterSpacing: '0.1em',
            }}
          >{k}</button>
        ))}
      </div>

      {state.status === 'loading' && (
        <div style={{
          fontFamily: 'var(--sb-font-mono)', fontSize: 12, color: 'var(--sb-fg-5)',
        }}>loading…</div>
      )}
      {state.status === 'empty' && (
        <EmptyState detail="Memory endpoint isn't online yet." />
      )}
      {state.status === 'ok' && state.items.length === 0 && (
        <EmptyState title="No memory entries" detail={`Nothing stored for kind: ${kind}.`} />
      )}
      {state.status === 'ok' && state.items.length > 0 && (
        <div style={{ border: '1px solid var(--sb-line)', background: 'var(--sb-card)' }}>
          {state.items.map((m, i) => (
            <div key={m.id} style={{
              display: 'flex', alignItems: 'flex-start', gap: 14,
              padding: '14px 16px',
              borderTop: i > 0 ? '1px solid var(--sb-line)' : 'none',
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
                }}>
                  <SBChip tone={toneFor(m.kind)}>{m.kind}</SBChip>
                  {m.source_ref && (
                    <span style={{
                      fontSize: 10.5, color: 'var(--sb-fg-5)',
                      fontFamily: 'var(--sb-font-mono)',
                    }}>{m.source_ref}</span>
                  )}
                  <span style={{
                    fontSize: 10.5, color: 'var(--sb-fg-5)',
                    fontFamily: 'var(--sb-font-mono)', marginLeft: 'auto',
                  }}>
                    used {m.used_count ?? 0}×
                  </span>
                </div>
                <div style={{
                  fontSize: 13, lineHeight: 1.55, color: 'var(--sb-fg-2)',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                }}>{m.content}</div>
              </div>
              <SBButton variant="ghost" size="xs" onClick={() => onDelete(m.id)}>
                <span style={{ color: 'var(--sb-hot)' }}>Delete</span>
              </SBButton>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function toneFor(kind) {
  if (kind === 'fact') return 'accent';
  if (kind === 'doc_chunk') return 'lime';
  if (kind === 'conversation_summary') return 'violet';
  return 'muted';
}
