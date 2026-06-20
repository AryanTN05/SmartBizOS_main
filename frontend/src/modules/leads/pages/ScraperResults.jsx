import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBCard, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { relTime } from '../lib/helpers.js';
import { toast } from '../lib/toast.jsx';

const SOURCE_LABELS = {
  producthunt:     'Product Hunt',
  hn_show_hn:      'Show HN',
  hn_hiring:       'HN hiring',
  techcrunch:      'TechCrunch',
  github_trending: 'GitHub trending',
  linkedin_seed:   'LinkedIn (seed)',
  directories:     'Directories',
  jobs:            'Job boards',
};

const STATUS_FILTERS = [
  { value: 'pending',   label: 'Pending' },
  { value: 'converted', label: 'Converted' },
  { value: 'dismissed', label: 'Dismissed' },
  { value: 'all',       label: 'All' },
];

const TIER_TONE = {
  HOT: { bg: 'rgba(255,90,106,0.15)', fg: 'var(--sb-hot)' },
  WARM: { bg: 'rgba(255,181,71,0.15)', fg: 'var(--sb-warm)' },
  NURTURE: { bg: 'var(--sb-panel)', fg: 'var(--sb-fg-3)' },
  DISQUALIFIED: { bg: 'transparent', fg: 'var(--sb-fg-5)' },
};

// Row status dot — green=enriched, amber=mid-flight, red=blocked, grey=raw.
function statusOf(r) {
  const e = r?.raw?.enrichment;
  if (!e) return { tone: 'grey', label: 'raw' };
  if (e.disqualifier) return { tone: 'red', label: 'disqualified' };
  if (e.score >= 70) return { tone: 'green', label: 'enriched' };
  if (e.score >= 40) return { tone: 'amber', label: 'enriched' };
  return { tone: 'red', label: 'low fit' };
}

function StatusDot({ tone }) {
  const c = { green: 'var(--sb-accent)', amber: 'var(--sb-warm)',
              red: 'var(--sb-hot)', grey: 'var(--sb-fg-5)' }[tone];
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: 0,
      background: c, flexShrink: 0,
    }} />
  );
}

function ScoreBadge({ enrichment }) {
  if (!enrichment || enrichment.score == null) {
    return <span style={{ fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>—</span>;
  }
  const tier = enrichment.tier || 'NURTURE';
  const tone = TIER_TONE[tier] || TIER_TONE.NURTURE;
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'baseline', gap: 6,
      padding: '3px 8px', background: tone.bg,
      border: `1px solid ${tone.fg}30`,
    }}>
      <span style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--sb-font-mono)', color: tone.fg }}>
        {enrichment.score}
      </span>
      <span style={{ fontSize: 9, fontFamily: 'var(--sb-font-mono)', letterSpacing: '0.08em', color: tone.fg }}>
        {tier}
      </span>
    </div>
  );
}

export default function ScraperResults() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('pending');
  const [busy, setBusy] = useState({});
  const [selected, setSelected] = useState(new Set());
  const [bulkRunning, setBulkRunning] = useState(false);
  const [enriching, setEnriching] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/api/scrapers/results?status=${filter}&limit=200`, { fresh: true });
      setItems(r?.items || []);
      setSelected(new Set());
    } catch (err) {
      if (err.status === 401) { window.location.href = '/admin/login'; return; }
      toast.error(err.message || 'Could not load results.');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh while a bulk enrichment is in flight so the user sees scores
  // populating in real time. Three safety nets:
  //   - only polls while filter === 'pending' (other filters never have
  //     ungraded rows so the loop would never converge)
  //   - hard cap of 120 ticks (~5min @ 2.5s) so the interval can't run for
  //     the page lifetime if the backend is wedged
  //   - clears on filter change too via the dep array
  useEffect(() => {
    if (!enriching) return;
    if (filter !== 'pending') {
      // User navigated away from the queue we were watching — stop.
      setEnriching(false);
      return;
    }
    let ticks = 0;
    const handle = setInterval(async () => {
      ticks++;
      try {
        const r = await api.get(`/api/scrapers/results?status=pending&limit=200`, { fresh: true });
        const next = r?.items || [];
        setItems(next);
        const stillUngraded = next.some((x) => !x?.raw?.enrichment);
        if (!stillUngraded || ticks >= 120) setEnriching(false);
      } catch (_) { /* keep trying until cap */ }
    }, 2500);
    return () => clearInterval(handle);
  }, [enriching, filter]);

  const toggleSelect = (id) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const selectAll = () => {
    if (selected.size === items.length) setSelected(new Set());
    else setSelected(new Set(items.map((r) => r.id)));
  };

  const convert = async (row) => {
    setBusy((b) => ({ ...b, [row.id]: 'convert' }));
    try {
      const r = await api.post(`/api/scrapers/results/${row.id}/convert`);
      toast.success('Converted to lead');
      setItems((xs) => xs.filter((x) => x.id !== row.id));
      setSelected((s) => { const n = new Set(s); n.delete(row.id); return n; });
      // Brief delay then offer to open the lead.
      setTimeout(() => navigate(`/admin/leads/${r.lead_id}`), 600);
    } catch (err) {
      if (err.status === 409 && err.details?.lead_id) toast.info('Already converted earlier.');
      else toast.error(err.message || 'Convert failed');
    } finally {
      setBusy((b) => { const n = { ...b }; delete n[row.id]; return n; });
    }
  };

  const dismiss = async (row) => {
    setBusy((b) => ({ ...b, [row.id]: 'dismiss' }));
    try {
      await api.post(`/api/scrapers/results/${row.id}/dismiss`);
      setItems((xs) => xs.filter((x) => x.id !== row.id));
      setSelected((s) => { const n = new Set(s); n.delete(row.id); return n; });
    } catch (err) {
      toast.error(err.message || 'Dismiss failed');
    } finally {
      setBusy((b) => { const n = { ...b }; delete n[row.id]; return n; });
    }
  };

  const reEnrich = async (row) => {
    setBusy((b) => ({ ...b, [row.id]: 'enrich' }));
    try {
      const r = await api.post(`/api/scrapers/results/${row.id}/enrich`);
      setItems((xs) => xs.map((x) => x.id === row.id ? r : x));
      toast.success('Re-enriched');
    } catch (err) {
      toast.error(err.message || 'Enrich failed');
    } finally {
      setBusy((b) => { const n = { ...b }; delete n[row.id]; return n; });
    }
  };

  const bulkConvert = async () => {
    if (selected.size === 0) return;
    setBulkRunning(true);
    let ok = 0;
    const failed = []; // capture per-id reasons so we can show "Failed: name (reason)" instead of swallowing
    for (const id of [...selected]) {
      try {
        await api.post(`/api/scrapers/results/${id}/convert`);
        ok++;
      } catch (e) {
        failed.push({ id, code: e?.code || 'error', message: e?.message || 'unknown' });
      }
    }
    if (failed.length === 0) {
      toast.success(`Converted ${ok} of ${selected.size}`);
    } else {
      const sample = failed.slice(0, 3).map((f) => f.code).join(', ');
      toast.error(`Converted ${ok}/${selected.size}. ${failed.length} failed (${sample}${failed.length > 3 ? '…' : ''})`);
    }
    setBulkRunning(false);
    load();
  };

  const bulkDismiss = async () => {
    if (selected.size === 0) return;
    setBulkRunning(true);
    let ok = 0;
    const failed = [];
    for (const id of [...selected]) {
      try {
        await api.post(`/api/scrapers/results/${id}/dismiss`);
        ok++;
      } catch (e) {
        failed.push({ id, code: e?.code || 'error' });
      }
    }
    if (failed.length === 0) {
      toast.success(`Dismissed ${ok} of ${selected.size}`);
    } else {
      const sample = failed.slice(0, 3).map((f) => f.code).join(', ');
      toast.error(`Dismissed ${ok}/${selected.size}. ${failed.length} failed (${sample}${failed.length > 3 ? '…' : ''})`);
    }
    setBulkRunning(false);
    load();
  };

  const bulkEnrichAll = async () => {
    setEnriching(true);
    try {
      const r = await api.post(`/api/scrapers/results/bulk/enrich?limit=50`);
      toast.info(`Enriching ${r.queued || 0} rows in background…`);
    } catch (err) {
      setEnriching(false);
      if (err.status === 409) {
        toast.info('Already enriching — wait for the current job to finish.');
      } else {
        toast.error(err.message || 'Enrich-all failed');
      }
    }
  };

  const ungraded = useMemo(() => items.filter((r) => !r?.raw?.enrichment).length, [items]);

  return (
    <div style={{ padding: '28px 32px', paddingBottom: 100 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 6 }}>Scraper captures</div>
          <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 600, margin: 0, letterSpacing: '-0.02em' }}>
            Review &amp; promote.
          </h1>
        </div>
        {filter === 'pending' && ungraded > 0 && (
          <SBButton variant="primary" size="sm" icon="spark"
            disabled={enriching} onClick={bulkEnrichAll}>
            {enriching ? `Enriching…` : `Enrich ${ungraded} ungraded`}
          </SBButton>
        )}
        <SBButton variant="ghost" size="sm" icon="arrow" onClick={() => navigate('/admin/scrapers')}>
          Back to scrapers
        </SBButton>
      </div>

      <div style={{
        display: 'flex', gap: 6, marginBottom: 18, padding: 4,
        background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
        width: 'fit-content',
      }}>
        {STATUS_FILTERS.map((f) => (
          <button key={f.value} onClick={() => setFilter(f.value)}
            style={{
              padding: '5px 12px', border: 'none',
              fontFamily: 'var(--sb-font-mono)', fontSize: 11, letterSpacing: '0.08em',
              textTransform: 'uppercase', cursor: 'pointer',
              background: filter === f.value ? 'var(--sb-accent-bg)' : 'transparent',
              color: filter === f.value ? 'var(--sb-accent)' : 'var(--sb-fg-4)',
            }}>{f.label}</button>
        ))}
      </div>

      {loading && items.length === 0 ? (
        <SkeletonRows count={5} />
      ) : items.length === 0 ? (
        <SBCard style={{ padding: 28, textAlign: 'center' }}>
          <div className="sb-label" style={{ color: 'var(--sb-fg-5)', marginBottom: 8 }}>nothing here</div>
          <div style={{ color: 'var(--sb-fg-4)', fontSize: 13 }}>
            {filter === 'pending'
              ? 'No new captures. Hit "Run now" on a scraper to pull fresh rows.'
              : `No ${filter} rows.`}
          </div>
        </SBCard>
      ) : (
        <>
          {/* Header / select-all */}
          <div style={{
            display: 'grid', gridTemplateColumns: '24px 14px 130px 1fr 90px auto',
            gap: 12, alignItems: 'center', padding: '8px 18px',
            fontSize: 10, fontFamily: 'var(--sb-font-mono)', letterSpacing: '0.1em',
            textTransform: 'uppercase', color: 'var(--sb-fg-5)',
            borderBottom: '1px solid var(--sb-line)',
          }}>
            <input type="checkbox"
              checked={selected.size > 0 && selected.size === items.length}
              ref={(el) => { if (el) el.indeterminate = selected.size > 0 && selected.size < items.length; }}
              onChange={selectAll}
              style={{ accentColor: 'var(--sb-accent)' }} />
            <span />
            <span>Source · Captured</span>
            <span>Lead</span>
            <span>Score</span>
            <span style={{ textAlign: 'right' }}>Actions</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {items.map((r) => {
              const e = r?.raw?.enrichment;
              const status = statusOf(r);
              const isSelected = selected.has(r.id);
              return (
                <div key={r.id} style={{
                  display: 'grid', gridTemplateColumns: '24px 14px 130px 1fr 90px auto',
                  gap: 12, alignItems: 'center', padding: '14px 18px',
                  borderBottom: '1px solid var(--sb-line)',
                  background: isSelected ? 'var(--sb-card)' : 'transparent',
                  transition: 'background 120ms',
                }}>
                  <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(r.id)}
                    style={{ accentColor: 'var(--sb-accent)' }} />
                  <StatusDot tone={status.tone} />

                  <div>
                    <SBChip tone="muted">{SOURCE_LABELS[r.source_type] || r.source_type}</SBChip>
                    <div style={{ fontSize: 10.5, color: 'var(--sb-fg-5)', marginTop: 4, fontFamily: 'var(--sb-font-mono)' }}>
                      {relTime(r.scraped_at_unix)}
                    </div>
                  </div>

                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--sb-fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.name || r.company || '(unnamed)'}
                      {r.name && r.company && <span style={{ color: 'var(--sb-fg-4)', fontWeight: 400 }}> · {r.company}</span>}
                    </div>
                    {(e?.description || r.raw?.summary) && (
                      <div style={{ fontSize: 12, color: 'var(--sb-fg-4)', marginTop: 4, lineHeight: 1.45,
                        overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                        {e?.description || r.raw?.summary}
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                      {r.url && (
                        <a href={r.url} target="_blank" rel="noreferrer" style={{
                          fontSize: 10.5, color: 'var(--sb-accent)', textDecoration: 'none',
                          fontFamily: 'var(--sb-font-mono)',
                        }}>
                          {(e?.domain || r.url.replace(/^https?:\/\//, '').split('/')[0]).slice(0, 60)} ↗
                        </a>
                      )}
                      {(e?.emails || []).slice(0, 1).map((em) => (
                        <span key={em} style={{
                          fontSize: 10.5, color: 'var(--sb-fg-3)', fontFamily: 'var(--sb-font-mono)',
                          padding: '1px 6px', background: 'var(--sb-panel)',
                        }}>✓ {em}</span>
                      ))}
                      {(e?.tech || []).slice(0, 4).map((t) => (
                        <span key={t} style={{
                          fontSize: 10, color: 'var(--sb-fg-4)',
                          padding: '1px 6px', background: 'var(--sb-panel)',
                          fontFamily: 'var(--sb-font-mono)',
                        }}>{t}</span>
                      ))}
                    </div>
                    {e?.reason && (
                      <div style={{ fontSize: 11, color: 'var(--sb-fg-5)', marginTop: 6, fontStyle: 'italic' }}>
                        {e.reason}
                      </div>
                    )}
                  </div>

                  <ScoreBadge enrichment={e} />

                  <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                    {r.status === 'pending' && (
                      <>
                        <SBButton variant="primary" size="xs" icon="check"
                          disabled={!!busy[r.id]} onClick={() => convert(r)}>
                          {busy[r.id] === 'convert' ? '…' : 'Convert'}
                        </SBButton>
                        <SBButton variant="ghost" size="xs" icon="spark"
                          disabled={!!busy[r.id]} onClick={() => reEnrich(r)}
                          title="Re-enrich (page fetch + ICP score)">
                          {busy[r.id] === 'enrich' ? '…' : ''}
                        </SBButton>
                        <SBButton variant="ghost" size="xs" icon="close"
                          disabled={!!busy[r.id]} onClick={() => dismiss(r)}>
                          {busy[r.id] === 'dismiss' ? '…' : ''}
                        </SBButton>
                      </>
                    )}
                    {r.status === 'converted' && r.converted_lead_id && (
                      <SBButton variant="ghost" size="xs" icon="arrow"
                        onClick={() => navigate(`/admin/leads/${r.converted_lead_id}`)}>
                        Open lead
                      </SBButton>
                    )}
                    {r.status === 'dismissed' && (
                      <span style={{ fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
                        dismissed
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Sticky bulk-action bar — appears only when something is selected */}
      {selected.size > 0 && (
        <div style={{
          position: 'fixed', left: 0, right: 0, bottom: 0,
          background: 'var(--sb-card-2)', borderTop: '1px solid var(--sb-line-2)',
          padding: '14px 32px', display: 'flex', alignItems: 'center', gap: 14,
          zIndex: 50, boxShadow: '0 -10px 30px rgba(0,0,0,0.4)',
          animation: 'sb-slide-up 200ms ease',
        }}>
          <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 12, color: 'var(--sb-accent)' }}>
            {selected.size} selected
          </span>
          <button onClick={() => setSelected(new Set())} style={{
            background: 'transparent', border: 'none', color: 'var(--sb-fg-5)',
            fontSize: 11, fontFamily: 'var(--sb-font-mono)', cursor: 'pointer',
          }}>clear</button>
          <div style={{ flex: 1 }} />
          <SBButton variant="primary" size="sm" icon="check"
            disabled={bulkRunning} onClick={bulkConvert}>
            {bulkRunning ? 'Working…' : `Convert ${selected.size}`}
          </SBButton>
          <SBButton variant="ghost" size="sm" icon="close"
            disabled={bulkRunning} onClick={bulkDismiss}>
            Dismiss {selected.size}
          </SBButton>
        </div>
      )}
    </div>
  );
}

function SkeletonRows({ count = 4 }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{
          padding: 18, background: 'var(--sb-card)',
          borderBottom: '1px solid var(--sb-line)',
          opacity: 1 - (i * 0.15),
        }}>
          <div style={{ height: 12, background: 'var(--sb-panel)', width: '20%', marginBottom: 8 }} />
          <div style={{ height: 16, background: 'var(--sb-panel)', width: '60%', marginBottom: 6 }} />
          <div style={{ height: 12, background: 'var(--sb-panel)', width: '85%' }} />
        </div>
      ))}
    </div>
  );
}
