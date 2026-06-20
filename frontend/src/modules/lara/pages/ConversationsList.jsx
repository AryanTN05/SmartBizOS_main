import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import EmptyState from '../components/EmptyState.jsx';

export default function ConversationsList() {
  const navigate = useNavigate();
  const [state, setState] = useState({ status: 'loading', items: [], next: null });
  const [renaming, setRenaming] = useState(null); // id currently being renamed
  const [renameValue, setRenameValue] = useState('');

  const load = async (cursor = null) => {
    try {
      const qs = new URLSearchParams({ limit: '50' });
      if (cursor) qs.set('cursor', cursor);
      const r = await api.get(`/api/conversations?${qs.toString()}`);
      // Backend returns {session_id, ...}; normalise to `id` so the rest of
      // the UI (rename/delete/navigate handlers) can use a single key.
      const items = (r?.items || []).map((c) => ({ ...c, id: c.id || c.session_id }));
      setState({ status: 'ok', items, next: r?.next_cursor || null });
    } catch (e) {
      setState({ status: 'empty', items: [], next: null, error: e });
    }
  };

  useEffect(() => {
    load();
    // Refresh triggers:
    //  - lara:conversation_added — fired by useLaraChat after a chat persists
    //  - focus / visibilitychange — covers the cross-page case (you finished a
    //    chat in the drawer on another route, then came back here)
    const onUpdate = () => load();
    const onVisible = () => { if (document.visibilityState === 'visible') load(); };
    window.addEventListener('lara:conversation_added', onUpdate);
    window.addEventListener('focus', onUpdate);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('lara:conversation_added', onUpdate);
      window.removeEventListener('focus', onUpdate);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  const doRename = async (id) => {
    const title = renameValue.trim();
    if (!title) { setRenaming(null); return; }
    try {
      await api.patch(`/api/conversations/${encodeURIComponent(id)}`, { title });
      setState((s) => ({ ...s, items: s.items.map((c) => c.id === id ? { ...c, title } : c) }));
    } catch (_) { /* swallow — backend may be absent */ }
    setRenaming(null);
  };

  const doDelete = async (id) => {
    if (!window.confirm('Delete this conversation?')) return;
    try { await api.delete(`/api/conversations/${encodeURIComponent(id)}`); } catch (_) { /* no-op */ }
    setState((s) => ({ ...s, items: s.items.filter((c) => c.id !== id) }));
  };

  return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 20,
      }}>
        <div>
          <div className="sb-label">M1 · Lara</div>
          <h1 style={{
            fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 500,
            margin: '6px 0 0', letterSpacing: '-0.02em',
          }}>Conversations</h1>
        </div>
        <SBButton variant="outline" size="sm" icon="lara" onClick={() => navigate('/admin/lara')}>
          Open Lara
        </SBButton>
      </div>

      {state.status === 'loading' && (
        <div style={{
          fontFamily: 'var(--sb-font-mono)', fontSize: 12, color: 'var(--sb-fg-5)',
          padding: '8px 0',
        }}>loading…</div>
      )}

      {state.status === 'empty' && (
        <EmptyState detail="Conversations endpoint isn't online yet." />
      )}

      {state.status === 'ok' && state.items.length === 0 && (
        <EmptyState title="No conversations" detail="Start one from the Lara page." />
      )}

      {state.status === 'ok' && state.items.length > 0 && (
        <div style={{ border: '1px solid var(--sb-line)', background: 'var(--sb-card)' }}>
          {state.items.map((c, i) => (
            <div key={c.id} style={{
              display: 'flex', alignItems: 'center', gap: 14,
              padding: '12px 16px',
              borderTop: i > 0 ? '1px solid var(--sb-line)' : 'none',
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                {renaming === c.id ? (
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => doRename(c.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') doRename(c.id);
                      if (e.key === 'Escape') setRenaming(null);
                    }}
                    style={{
                      width: '100%', background: 'var(--sb-panel)',
                      border: '1px solid var(--sb-line-3)', color: 'var(--sb-fg)',
                      padding: '5px 8px', fontSize: 13, fontFamily: 'var(--sb-font)',
                      outline: 'none',
                    }}
                  />
                ) : (
                  <div
                    onClick={() => navigate(`/admin/conversations/${encodeURIComponent(c.id)}`)}
                    style={{
                      fontSize: 13.5, color: 'var(--sb-fg)', fontWeight: 500,
                      cursor: 'pointer',
                    }}
                  >
                    {c.title || 'Untitled'}
                  </div>
                )}
                <div style={{
                  fontSize: 11, color: 'var(--sb-fg-5)', marginTop: 3,
                  fontFamily: 'var(--sb-font-mono)',
                }}>
                  {c.message_count ?? 0} msgs · updated {fmtTime(c.updated_at_unix)}
                </div>
              </div>
              <SBChip tone={c.kind === 'admin' ? 'accent' : 'violet'}>{c.kind}</SBChip>
              <SBButton
                variant="ghost" size="xs"
                onClick={() => { setRenaming(c.id); setRenameValue(c.title || ''); }}
              >Rename</SBButton>
              <SBButton variant="ghost" size="xs" onClick={() => doDelete(c.id)}>
                <span style={{ color: 'var(--sb-hot)' }}>Delete</span>
              </SBButton>
              <button
                onClick={() => navigate(`/admin/conversations/${c.id}`)}
                style={{
                  background: 'transparent', border: 'none', color: 'var(--sb-fg-4)',
                  cursor: 'pointer', padding: 4,
                }}
                aria-label="Open"
              >
                <SBIcon name="chevronR" size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {state.next && (
        <div style={{ marginTop: 16 }}>
          <SBButton variant="outline" size="sm" onClick={() => load(state.next)}>
            Load more
          </SBButton>
        </div>
      )}
    </div>
  );
}

function fmtTime(unix) {
  if (!unix) return '—';
  try {
    const d = new Date(unix * 1000);
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch (_) { return '—'; }
}
