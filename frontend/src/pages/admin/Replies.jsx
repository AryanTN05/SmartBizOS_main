import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../lib/api.js';
import { SBButton, SBCard, SBChip, SBIcon, SBSkeleton } from '../../components/primitives';

// /admin/replies — incoming email replies surfaced from the IMAP poller.
// The poller writes Lead.last_reply_intent + last_reply_at; this page is the
// triage view for "who replied since I last checked?"
//
// Why a dedicated page: the existing /admin/inbox is for scraper captures
// (rubric + convert). Replies are a different mental model (read + decide
// next step), so they get their own surface.

const INTENT_TONES = {
  positive:     { tone: 'hot',   label: 'positive',     advice: 'Reply same-day.' },
  negative:     { tone: 'cool',  label: 'negative',     advice: 'Mark closed; consider re-engaging in 90d.' },
  neutral:      { tone: 'muted', label: 'neutral',      advice: 'Send the next nudge.' },
  wrong_person: { tone: 'warm',  label: 'wrong contact',advice: 'Ask for the right contact.' },
  unsubscribe:  { tone: 'cool',  label: 'unsubscribe',  advice: 'Suppress + close.' },
  auto_reply:   { tone: 'muted', label: 'auto-reply',   advice: 'Re-queue for the date they’re back.' },
};

const INTENT_TABS = [null, 'positive', 'negative', 'neutral', 'wrong_person', 'unsubscribe', 'auto_reply'];

export default function Replies() {
  const navigate = useNavigate();
  const [items, setItems] = useState(null);
  const [total, setTotal] = useState(0);
  const [intent, setIntent] = useState(null);

  const load = async (filterIntent = intent) => {
    try {
      const qs = new URLSearchParams({ limit: '50' });
      if (filterIntent) qs.set('intent', filterIntent);
      const r = await api.get(`/api/leads/replies?${qs.toString()}`, { fresh: true });
      setItems(r?.items || []);
      setTotal(r?.total_estimate ?? (r?.items || []).length);
    } catch (e) {
      setItems([]);
      setTotal(0);
    }
  };

  useEffect(() => {
    load(intent);
    const onUpdate = () => load(intent);
    const onVisible = () => { if (document.visibilityState === 'visible') load(intent); };
    window.addEventListener('lara:lead_updated', onUpdate);
    window.addEventListener('focus', onUpdate);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('lara:lead_updated', onUpdate);
      window.removeEventListener('focus', onUpdate);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [intent]);

  return (
    <div style={{ padding: '20px 28px', maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>Email replies</div>
          <div className="sb-label">{total} total · ordered by most recent</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
        {INTENT_TABS.map((t) => (
          <SBButton
            key={String(t)}
            variant={intent === t ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setIntent(t)}
          >
            {t === null ? 'All' : (INTENT_TONES[t]?.label || t)}
          </SBButton>
        ))}
      </div>

      {items === null && <SBSkeleton lines={4} />}
      {items !== null && items.length === 0 && (
        <SBCard>
          <div style={{ padding: 24, color: 'var(--sb-fg-5)', fontSize: 13 }}>
            No replies yet{intent ? ` for "${INTENT_TONES[intent]?.label}"` : ''}.
            {' '}Replies appear here automatically once the IMAP poller classifies them.
            {' '}Confirm <code>IMAP_ENCRYPTION_KEY</code> is set and an inbox is configured in Settings.
          </div>
        </SBCard>
      )}

      {(items || []).map((lead) => {
        const tone = INTENT_TONES[lead.last_reply_intent] || INTENT_TONES.neutral;
        return (
          <div
            key={lead.id}
            onClick={() => navigate(`/admin/leads/${lead.id}`)}
            style={{
              padding: 14, borderBottom: '1px solid var(--sb-line)',
              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 14,
            }}
          >
            <SBIcon name="leads" size={18} stroke={1.4} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--sb-fg)' }}>
                {lead.name || '(no name)'}
                <span style={{ color: 'var(--sb-fg-5)', fontWeight: 400, marginLeft: 8 }}>
                  {lead.company_name ? ` · ${lead.company_name}` : ''}
                </span>
              </div>
              <div style={{
                fontSize: 11, color: 'var(--sb-fg-5)',
                fontFamily: 'var(--sb-font-mono)', marginTop: 3,
              }}>
                {lead.last_reply_at_unix
                  ? new Date(lead.last_reply_at_unix * 1000).toLocaleString()
                  : '—'}
                {' · '}{tone.advice}
              </div>
            </div>
            <SBChip tone={tone.tone}>{tone.label}</SBChip>
            <SBIcon name="chevron-right" size={14} stroke={1.4} />
          </div>
        );
      })}
    </div>
  );
}
