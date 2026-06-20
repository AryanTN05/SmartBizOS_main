import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBCard, SBChip, SBIcon, SBSkeleton } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../lib/toast.jsx';
import { triggerMeta } from '../lib/helpers.js';

// Account-level rollup of /admin/leads. Same data, ABM lens — group leads
// by company_domain (or company_name fallback). Answers "which accounts
// are heating up?" without scrolling through individual rows.

const SORTS = [
  { key: 'hot',     label: 'most hot' },
  { key: 'replied', label: 'most replied' },
  { key: 'recent',  label: 'recent activity' },
];

export default function Accounts() {
  const navigate = useNavigate();
  const [items, setItems] = useState(null);
  const [total, setTotal] = useState(0);
  const [sort, setSort] = useState('hot');
  const [q, setQ] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get(`/api/leads/accounts?sort=${sort}&limit=200`, { fresh: true });
        if (cancelled) return;
        setItems(r?.items || []);
        setTotal(r?.total ?? 0);
      } catch (err) {
        if (err.status === 401) { window.location.href = '/admin/login'; return; }
        toast.error(err?.message || 'Could not load accounts');
        setItems([]);
      }
    })();
    return () => { cancelled = true; };
  }, [sort]);

  const filtered = useMemo(() => {
    if (!items) return [];
    if (!q.trim()) return items;
    const s = q.trim().toLowerCase();
    return items.filter((a) =>
      (a.company_name || '').toLowerCase().includes(s) ||
      (a.company_domain || '').toLowerCase().includes(s),
    );
  }, [items, q]);

  return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{ marginBottom: 18 }}>
        <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 6 }}>Accounts</div>
        <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 600, margin: 0, letterSpacing: '-0.02em' }}>
          Heating up. <span style={{ color: 'var(--sb-fg-5)' }}>By company.</span>
        </h1>
        <p style={{ marginTop: 8, color: 'var(--sb-fg-4)', fontSize: 13, lineHeight: 1.55, maxWidth: 560 }}>
          Same leads, grouped by company. Useful when one account has multiple
          contacts and you want a single ABM-flavored view of how warm it is.
        </p>
      </div>

      <div style={{
        display: 'flex', gap: 8, alignItems: 'center',
        marginBottom: 14, flexWrap: 'wrap',
      }}>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter by name or domain…"
          style={{
            flex: 1, minWidth: 220, maxWidth: 360,
            background: 'var(--sb-panel)', color: 'var(--sb-fg)',
            border: '1px solid var(--sb-line-2)', padding: '8px 12px',
            fontSize: 12.5, fontFamily: 'var(--sb-font-mono)', outline: 'none',
          }}
        />
        <span style={{
          fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
          textTransform: 'uppercase', letterSpacing: '0.08em', marginLeft: 8,
        }}>sort</span>
        {SORTS.map((s) => (
          <button key={s.key} onClick={() => setSort(s.key)}
            style={{
              padding: '5px 10px',
              background: sort === s.key ? 'var(--sb-accent-bg)' : 'transparent',
              border: `1px solid ${sort === s.key ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
              color: sort === s.key ? 'var(--sb-accent)' : 'var(--sb-fg-3)',
              cursor: 'pointer', fontSize: 11,
              fontFamily: 'var(--sb-font-mono)',
              textTransform: 'uppercase', letterSpacing: '0.06em',
            }}>{s.label}</button>
        ))}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
          {filtered.length} of {total}
        </span>
      </div>

      {items === null && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {Array.from({ length: 5 }).map((_, i) => (
            <SBSkeleton key={i} variant="card" h={66} style={{ opacity: Math.max(0.3, 1 - i * 0.15) }} />
          ))}
        </div>
      )}
      {items && filtered.length === 0 && (
        <SBCard style={{ padding: 32, textAlign: 'center' }}>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>
            {q ? 'No matches' : 'No accounts yet'}
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--sb-fg-4)', lineHeight: 1.6, maxWidth: 440, margin: '0 auto' }}>
            {q
              ? `Nothing matches "${q}". Try a different name or clear the filter.`
              : 'Accounts populate automatically as you convert leads from the Inbox. They group multiple contacts at the same company so you can see who\'s heating up at a glance.'}
          </div>
          {!q && (
            <div style={{ marginTop: 14 }}>
              <SBButton variant="primary" size="sm" iconRight="arrow"
                onClick={() => navigate('/admin/inbox')}>
                Go to Inbox
              </SBButton>
            </div>
          )}
        </SBCard>
      )}

      {filtered.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filtered.map((a) => (
            <AccountRow key={a.key} a={a}
              onOpen={() => navigate(`/admin/leads?q=${encodeURIComponent(a.company_name || a.company_domain || '')}`)} />
          ))}
        </div>
      )}
    </div>
  );
}

function AccountRow({ a, onOpen }) {
  const heatTone = a.hot_count > 0 ? 'hot' : a.replied_count > 0 ? 'lime' : 'neutral';
  return (
    <SBCard style={{ padding: '14px 18px', cursor: 'pointer' }} onClick={onOpen}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{
          width: 32, height: 32, background: 'var(--sb-panel)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--sb-accent)', border: '1px solid var(--sb-line-2)',
        }}>
          <SBIcon name="building" size={14} stroke={1.6} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--sb-fg)' }}>
            {a.company_name}
          </div>
          {a.company_domain && (
            <div style={{ fontSize: 11.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
              {a.company_domain}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {(a.triggers || []).slice(0, 3).map((t) => {
            const m = triggerMeta(t);
            return <SBChip key={t} tone={m.tone} icon={m.icon}>{m.label}</SBChip>;
          })}
        </div>

        <div style={{ display: 'flex', gap: 18, alignItems: 'baseline', fontFamily: 'var(--sb-font-mono)' }}>
          <Stat label="leads"   value={a.lead_count}    tone="neutral" />
          <Stat label="hot"     value={a.hot_count}     tone={a.hot_count > 0 ? 'hot' : 'muted'} />
          <Stat label="replied" value={a.replied_count} tone={a.replied_count > 0 ? 'lime' : 'muted'} />
          <Stat label="avg"     value={a.avg_score}     tone="muted" />
        </div>

        <SBChip tone={heatTone} icon={a.hot_count > 0 ? 'flame' : 'dot'}>
          {a.hot_count > 0 ? 'hot' : a.replied_count > 0 ? 'engaged' : 'cold'}
        </SBChip>
      </div>
    </SBCard>
  );
}

function Stat({ label, value, tone }) {
  const COLOR = {
    hot: 'var(--sb-hot)', lime: 'var(--sb-lime)', neutral: 'var(--sb-fg-2)',
    muted: 'var(--sb-fg-5)',
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', minWidth: 36 }}>
      <span style={{ fontSize: 16, fontWeight: 600, color: COLOR[tone] || COLOR.neutral, lineHeight: 1 }}>
        {value}
      </span>
      <span style={{
        fontSize: 9.5, color: 'var(--sb-fg-5)', textTransform: 'uppercase',
        letterSpacing: '0.08em', marginTop: 3,
      }}>{label}</span>
    </div>
  );
}
