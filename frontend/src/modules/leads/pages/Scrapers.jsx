import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBCard, SBChip, SBIcon, SBSkeleton } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { relTime } from '../lib/helpers.js';
import { toast } from '../lib/toast.jsx';

// /admin/scrapers — list of configured scrapers with schedule, enabled, last
// run state. Toggle enabled, "Run now", "Dry run". LinkedIn scraper is hard-
// disabled per legal; surface the `notes` field in the UI.

const SOURCE_LABELS = {
  producthunt: 'Product Hunt',
  directory_clutch: 'Clutch Directory',
  reviews_g2: 'G2 Reviews',
  linkedin_seed: 'LinkedIn (seeded only)',
};

const STATUS_TONE = {
  success: 'accent',
  partial: 'warm',
  failed: 'hot',
  running: 'cool',
};

export default function Scrapers() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pendingCount, setPendingCount] = useState(0);
  // Per-scraper inflight state so the row can show "Running…" + a pulse dot
  // while the POST /run + auto-enrichment chain is executing on the server.
  const [running, setRunning] = useState({});

  useEffect(() => {
    let cancelled = false;
    api.get('/api/scrapers/results/_count').then((r) => {
      if (!cancelled) setPendingCount(r?.pending || 0);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const fetchList = useCallback(async () => {
    try {
      const res = await api.get('/api/scrapers');
      setItems(res.items || []);
    } catch (err) {
      if (err.status === 401) {
        window.location.href = '/admin/login';
      } else {
        toast.error(err.message || 'Could not load scrapers.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  const toggleEnabled = async (sc) => {
    const next = !sc.enabled;
    const prev = items;
    setItems((is) => is.map((i) => (i.id === sc.id ? { ...i, enabled: next } : i)));
    try {
      const res = await api.patch(`/api/scrapers/${sc.id}`, { enabled: next });
      const fresh = res.scraper || res;
      setItems((is) => is.map((i) => (i.id === sc.id ? fresh : i)));
    } catch (err) {
      setItems(prev);
      if (err.status === 422 && err.details?.reason === 'linkedin_live_scraping_disabled') {
        toast.error('Hard-disabled per legal — see notes.');
      } else {
        toast.error(err.message || 'Toggle failed');
      }
    }
  };

  const runNow = async (sc) => {
    if (running[sc.id]) return;  // already in flight, ignore double-clicks
    setRunning((r) => ({ ...r, [sc.id]: true }));
    try {
      const res = await api.post(`/api/scrapers/${sc.id}/run`);
      const inserted = res.inserted ?? 0;
      if (res.status === 'completed' && inserted > 0) {
        toast.success(`${sc.name} · captured ${inserted} new — enriching in background`);
      } else if (res.status === 'completed') {
        toast.info(`${sc.name} · ran clean, nothing new to add`);
      } else if (res.error) {
        toast.error(`${sc.name} failed: ${res.error.slice(0, 80)}`);
      } else {
        toast.info(`${sc.name} queued`);
      }
      setTimeout(fetchList, 1500);
      api.get('/api/scrapers/results/_count').then((r) => setPendingCount(r?.pending || 0)).catch(() => {});
    } catch (err) {
      toast.error(err.message || 'Run failed');
    } finally {
      setRunning((r) => { const n = { ...r }; delete n[sc.id]; return n; });
    }
  };

  return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{ marginBottom: 20, display: 'flex', alignItems: 'flex-start', gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 8 }}>Scrapers</div>
          <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 30, fontWeight: 600, margin: 0, letterSpacing: '-0.02em' }}>
            Lead pipelines, <span style={{ color: 'var(--sb-fg-5)' }}>running quietly.</span>
          </h1>
          <p style={{ marginTop: 10, color: 'var(--sb-fg-4)', fontSize: 13, lineHeight: 1.6, maxWidth: 560 }}>
            Cron-driven scrapers that feed the Kanban. Configured in code; toggled and
            kicked off here. LinkedIn is seeded-only per the hiQ legal settlement.
          </p>
        </div>
        <SBButton
          variant={pendingCount > 0 ? 'primary' : 'ghost'}
          size="sm"
          icon="eye"
          onClick={() => navigate('/admin/scrapers/results')}
        >
          {pendingCount > 0 ? `Review ${pendingCount} captured` : 'Review captures'}
        </SBButton>
      </div>


      {loading && items.length === 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <SBSkeleton key={i} variant="card" h={84} style={{ opacity: Math.max(0.3, 1 - i * 0.18) }} />
          ))}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {items.map((sc) => (
            <SBCard key={sc.id} style={{ padding: 18 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                <div style={{
                  width: 36, height: 36, background: 'var(--sb-panel)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: sc.enabled ? 'var(--sb-accent)' : 'var(--sb-fg-5)',
                  border: '1px solid var(--sb-line-2)', flexShrink: 0,
                }}>
                  <SBIcon name="leads" size={14} stroke={1.5} />
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>
                      {SOURCE_LABELS[sc.source] || sc.source}
                    </div>
                    <EnabledChip enabled={sc.enabled} />
                    {sc.last_run_status && !running[sc.id] && (
                      <SBChip tone={STATUS_TONE[sc.last_run_status] || 'muted'}>
                        {sc.last_run_status}
                      </SBChip>
                    )}
                    {running[sc.id] && (
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 6,
                        padding: '2px 8px', background: 'var(--sb-accent-bg)',
                        color: 'var(--sb-accent)', fontSize: 10.5,
                        fontFamily: 'var(--sb-font-mono)', letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                      }}>
                        <span style={{
                          width: 6, height: 6, borderRadius: '50%',
                          background: 'var(--sb-accent)',
                          animation: 'sb-pulse 1.2s ease-in-out infinite',
                        }} />
                        Running
                      </span>
                    )}
                  </div>

                  <div style={{
                    display: 'flex', gap: 16, flexWrap: 'wrap',
                    marginTop: 8, fontSize: 11.5, color: 'var(--sb-fg-4)',
                    fontFamily: 'var(--sb-font-mono)',
                  }}>
                    <span>schedule: {sc.schedule || 'manual'}</span>
                    <span>last run: {relTime(sc.last_run_at_unix)}</span>
                    <span>added: {sc.last_run_leads_added ?? 0}</span>
                  </div>

                  {sc.notes && (
                    <div style={{
                      marginTop: 10, padding: '8px 12px',
                      background: 'var(--sb-bg-2)', border: '1px solid var(--sb-line)',
                      fontSize: 11.5, color: 'var(--sb-fg-4)',
                      fontFamily: 'var(--sb-font-mono)', lineHeight: 1.55,
                    }}>
                      <SBIcon name="warn" size={11} stroke={1.6} /> {sc.notes}
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                  <SBButton
                    variant={sc.enabled ? 'ghost' : 'secondary'}
                    size="sm"
                    icon={sc.enabled ? 'close' : 'check'}
                    onClick={() => toggleEnabled(sc)}
                  >
                    {sc.enabled ? 'Disable' : 'Enable'}
                  </SBButton>
                  <SBButton
                    variant="primary" size="sm" icon="bolt"
                    onClick={() => runNow(sc)}
                    disabled={!sc.enabled || !!running[sc.id]}
                  >
                    {running[sc.id] ? 'Running…' : 'Run now'}
                  </SBButton>
                </div>
              </div>
            </SBCard>
          ))}
        </div>
      )}
    </div>
  );
}

function EnabledChip({ enabled }) {
  return enabled
    ? <SBChip tone="accent" icon="dot">enabled</SBChip>
    : <SBChip tone="muted">disabled</SBChip>;
}
