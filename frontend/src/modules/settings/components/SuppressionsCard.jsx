import React, { useEffect, useState } from 'react';
import { SBButton, SBCard, SBChip } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../../leads/lib/toast.jsx';

// Suppression list management. Auto-populated by:
//   - 1-click unsubscribe clicks (RFC 8058 List-Unsubscribe)
//   - Resend webhook (hard bounces, soft bounces ×3, complaints)
// And manually by the user via this card.
//
// The scheduler hard-blocks any send_* step when the recipient is on the
// list, so this is the authoritative "do not contact" surface. Removing
// a row re-enables sending — used carefully when you genuinely want to
// re-engage someone.

const REASON_LABEL = {
  manual:      { label: 'manual',     tone: 'muted' },
  user_unsub:  { label: 'unsubscribed', tone: 'hot' },
  bounce_hard: { label: 'hard bounce',  tone: 'hot' },
  bounce_soft: { label: 'soft bounce',  tone: 'warm' },
  complained:  { label: 'spam complaint', tone: 'hot' },
};

export default function SuppressionsCard() {
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ email: '', notes: '' });

  const refresh = async () => {
    try {
      const r = await api.get('/api/workspace/settings/suppressions', { fresh: true });
      setItems(r?.items || []);
    } catch (err) {
      toast.error(err?.message || 'Could not load suppressions');
      setItems([]);
    }
  };
  useEffect(() => { refresh(); }, []);

  const onAdd = async () => {
    if (!draft.email || !draft.email.includes('@')) {
      toast.error('Enter a valid email');
      return;
    }
    setBusy(true);
    try {
      await api.post('/api/workspace/settings/suppressions', {
        email: draft.email.trim().toLowerCase(),
        reason: 'manual',
        notes: draft.notes || null,
      });
      toast.success(`Suppressed · ${draft.email}`);
      setAdding(false);
      setDraft({ email: '', notes: '' });
      await refresh();
    } catch (err) {
      toast.error(err?.message || 'Add failed');
    } finally {
      setBusy(false);
    }
  };

  const onRemove = async (email) => {
    if (!window.confirm(`Remove ${email} from the suppression list? This re-enables sending to them.`)) return;
    try {
      await api.delete(`/api/workspace/settings/suppressions?email=${encodeURIComponent(email)}`);
      toast.info(`Removed · ${email}`);
      await refresh();
    } catch (err) {
      toast.error(err?.message || 'Remove failed');
    }
  };

  return (
    <SBCard style={{ padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Suppression list</span>
            <SBChip tone="muted">{(items || []).length}</SBChip>
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', lineHeight: 1.5 }}>
            Recipients who hit the unsubscribe link, hard-bounced, or
            complained land here automatically. The scheduler refuses to
            send to anyone on the list — required for Google + Microsoft
            bulk-sender rules.
          </div>
        </div>
        {!adding && (
          <SBButton variant="ghost" size="xs" icon="plus" onClick={() => setAdding(true)}>
            Add manually
          </SBButton>
        )}
      </div>

      {adding && (
        <div style={{
          marginBottom: 14, padding: 14,
          background: 'var(--sb-panel)', border: '1px solid var(--sb-line-2)',
          display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <input
            value={draft.email}
            onChange={(e) => setDraft({ ...draft, email: e.target.value })}
            placeholder="email@example.com"
            style={inputMono}
          />
          <input
            value={draft.notes}
            onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            placeholder="reason (optional)"
            style={inputMono}
          />
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            <SBButton variant="ghost" size="xs" onClick={() => { setAdding(false); setDraft({ email: '', notes: '' }); }}>
              Cancel
            </SBButton>
            <SBButton variant="primary" size="xs" icon="check" onClick={onAdd} disabled={busy || !draft.email}>
              {busy ? 'Adding…' : 'Suppress'}
            </SBButton>
          </div>
        </div>
      )}

      {items === null && (
        <div style={{ fontSize: 12, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
          ▸ loading…
        </div>
      )}
      {items && items.length === 0 && (
        <div style={{
          padding: '12px 14px', fontSize: 12, color: 'var(--sb-fg-5)',
          fontFamily: 'var(--sb-font-mono)', textAlign: 'center',
          border: '1px dashed var(--sb-line-2)',
        }}>
          ▸ no suppressions yet — bounces and unsubscribes will appear here
        </div>
      )}
      {items && items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {items.map((s) => {
            const rl = REASON_LABEL[s.reason] || { label: s.reason, tone: 'muted' };
            return (
              <div key={s.id} style={{
                display: 'grid', gridTemplateColumns: '1fr 110px 80px',
                gap: 10, alignItems: 'center', padding: '6px 10px',
                borderBottom: '1px solid var(--sb-line)',
              }}>
                <span style={{ fontSize: 12, fontFamily: 'var(--sb-font-mono)', color: 'var(--sb-fg-2)',
                                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.email}
                </span>
                <SBChip tone={rl.tone}>{rl.label}</SBChip>
                <SBButton variant="ghost" size="xs" onClick={() => onRemove(s.email)}>
                  Remove
                </SBButton>
              </div>
            );
          })}
        </div>
      )}
    </SBCard>
  );
}

const inputMono = {
  width: '100%', boxSizing: 'border-box',
  padding: '7px 10px',
  background: 'var(--sb-bg)', color: 'var(--sb-fg)',
  border: '1px solid var(--sb-line-2)',
  fontSize: 12, fontFamily: 'var(--sb-font-mono)',
  outline: 'none',
};
