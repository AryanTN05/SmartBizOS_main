import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { SBButton, SBChip } from '../../../components/primitives';
import api from '../../../lib/api.js';
import RunListItem from '../components/RunListItem.jsx';
import RunDetail from '../components/RunDetail.jsx';
import OfflineBanner from '../components/OfflineBanner.jsx';
import StartRunModal from '../components/StartRunModal.jsx';

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'running', label: 'Running' },
  { value: 'paused', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
];

// Runs list + detail split-view.
// Handles:
//  - filter chips → re-query
//  - row click → navigate & fetch detail
//  - polling while detail run is in "running" state
//  - optimistic pause/cancel (revert on 502)
export default function AutomationView() {
  const navigate = useNavigate();
  const { run_id: runIdParam } = useParams();

  const [runs, setRuns] = useState([]);
  const [runsError, setRunsError] = useState(null); // ApiError | null
  const [runsLoading, setRunsLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');

  const [selectedId, setSelectedId] = useState(runIdParam || null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [actionState, setActionState] = useState({ inflight: null, error: null });

  const [startModalOpen, setStartModalOpen] = useState(false);

  // Keep URL + selection in sync.
  useEffect(() => { setSelectedId(runIdParam || null); }, [runIdParam]);

  // Lead-name cache for the left rail.
  const leadCacheRef = useRef(new Map());
  const [leadCacheVersion, setLeadCacheVersion] = useState(0);

  const loadRuns = useCallback(async (opts = {}) => {
    setRunsLoading(true);
    try {
      const qs = new URLSearchParams();
      qs.set('limit', '25');
      if (opts.status ?? filterStatus) qs.set('status', opts.status ?? filterStatus);
      const r = await api.get(`/api/automations/runs?${qs.toString()}`);
      const items = r?.items || [];
      setRuns(items);
      setRunsError(null);
      return items;
    } catch (e) {
      if (e.code === 'unauthenticated') {
        navigate('/admin/login');
        return [];
      }
      setRunsError(e);
      setRuns([]);
      return [];
    } finally {
      setRunsLoading(false);
    }
  }, [filterStatus, navigate]);

  // Initial + filter-change load.
  useEffect(() => { loadRuns(); }, [loadRuns]);

  // Lazy-resolve lead names for visible runs (batch-cache).
  useEffect(() => {
    const missing = runs
      .map((r) => r.lead_id)
      .filter((id) => id && !leadCacheRef.current.has(id));
    if (missing.length === 0) return;
    let cancelled = false;
    (async () => {
      // Fire one-by-one with small concurrency. 25 items max per page so this is fine.
      await Promise.all(missing.slice(0, 10).map(async (id) => {
        try {
          const l = await api.get(`/api/leads/${id}`);
          if (!cancelled && l) {
            leadCacheRef.current.set(id, {
              name: `${l.first_name || ''} ${l.last_name || ''}`.trim() || l.email,
              company: l.company || null,
            });
          }
        } catch (_e) {
          // No-op — server now returns lead_name/lead_company in the run row.
        }
      }));
      if (!cancelled) setLeadCacheVersion((v) => v + 1);
    })();
    return () => { cancelled = true; };
  }, [runs]);

  // Detail fetcher — split out so polling can reuse it.
  const loadDetail = useCallback(async (id) => {
    if (!id) { setDetail(null); return null; }
    try {
      const r = await api.get(`/api/automations/runs/${id}`);
      setDetail(r);
      setDetailError(null);
      return r;
    } catch (e) {
      if (e.code === 'unauthenticated') { navigate('/admin/login'); return null; }
      setDetailError(e);
      setDetail(null);
      return null;
    }
  }, [navigate]);

  // Load detail when selection changes.
  useEffect(() => { loadDetail(selectedId); }, [selectedId, loadDetail]);

  // Poll while running.
  useEffect(() => {
    if (!detail?.run) return;
    if (detail.run.status !== 'running') return;
    const handle = setInterval(() => {
      loadDetail(detail.run.id);
    }, 5000);
    return () => clearInterval(handle);
  }, [detail?.run?.id, detail?.run?.status, loadDetail]);

  const selectRun = (id) => {
    navigate(`/admin/automations/${id}`);
    setSelectedId(id);
  };

  // Optimistic action helper. `mutation` is a function returning a promise;
  // we flip the UI immediately, then revert on 502.
  const runAction = async (kind, optimisticStatus, path) => {
    if (!detail?.run) return;
    const prev = detail;
    setActionState({ inflight: kind, error: null });
    setDetail((d) => d ? ({ ...d, run: { ...d.run, status: optimisticStatus } }) : d);
    setRuns((rs) => rs.map((r) => r.id === prev.run.id ? { ...r, status: optimisticStatus } : r));
    try {
      const r = await api.post(path);
      const updated = r?.run || r;
      if (updated) {
        setDetail((d) => d ? ({ ...d, run: { ...d.run, ...updated } }) : d);
        setRuns((rs) => rs.map((row) => row.id === updated.id ? { ...row, ...updated } : row));
      }
      setActionState({ inflight: null, error: null });
    } catch (e) {
      // Revert.
      setDetail(prev);
      setRuns((rs) => rs.map((r) => r.id === prev.run.id ? { ...r, status: prev.run.status } : r));
      setActionState({ inflight: null, error: e });
    }
  };

  const handlePause = () => runAction('pause', 'paused', `/api/automations/runs/${detail.run.id}/pause`);
  const handleCancel = () => runAction('cancel', 'cancelled', `/api/automations/runs/${detail.run.id}/cancel`);

  const handleRunCreated = (run) => {
    if (!run?.id) { loadRuns(); return; }
    setRuns((rs) => [run, ...rs.filter((r) => r.id !== run.id)]);
    selectRun(run.id);
  };

  const filteredRuns = useMemo(() => runs, [runs, leadCacheVersion]);
  const leadCache = leadCacheRef.current;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', height: 'calc(100vh - 60px - 44px)' }}>
      {/* Left rail */}
      <div style={{ borderRight: '1px solid var(--sb-line)', overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        <div style={{
          padding: '14px 20px', borderBottom: '1px solid var(--sb-line)',
          display: 'flex', alignItems: 'center', gap: 8, position: 'sticky', top: 0,
          background: 'var(--sb-bg)', zIndex: 1,
        }}>
          <span className="sb-label">Runs</span>
          <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-4)' }}>
            {runsLoading ? '…' : runs.length}
          </span>
          <div style={{ flex: 1 }} />
          <SBButton variant="primary" size="xs" icon="plus" onClick={() => setStartModalOpen(true)}>
            Start
          </SBButton>
        </div>

        {/* Filter chips */}
        <div style={{
          padding: '10px 16px', borderBottom: '1px solid var(--sb-line)',
          display: 'flex', gap: 6, flexWrap: 'wrap',
        }}>
          {STATUS_FILTERS.map((f) => {
            const active = filterStatus === f.value;
            return (
              <button
                key={f.value || 'all'}
                onClick={() => setFilterStatus(f.value)}
                style={{
                  padding: '3px 9px', fontSize: 10.5,
                  fontFamily: 'var(--sb-font-mono)', letterSpacing: '0.08em',
                  textTransform: 'uppercase', fontWeight: 600,
                  background: active ? 'var(--sb-accent-bg)' : 'transparent',
                  color: active ? 'var(--sb-accent)' : 'var(--sb-fg-4)',
                  border: `1px solid ${active ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
                  cursor: 'pointer',
                }}
              >
                {f.label}
              </button>
            );
          })}
        </div>

        {runsError && <OfflineBanner code={runsError.code} />}

        {filteredRuns.length === 0 && !runsLoading && (
          <div style={{
            padding: 32, textAlign: 'center', color: 'var(--sb-fg-5)',
            fontFamily: 'var(--sb-font-mono)', fontSize: 11,
          }}>
            no runs in this filter
          </div>
        )}

        {filteredRuns.map((r) => {
          const cached = leadCache.get(r.lead_id);
          // Server now returns lead_name + lead_company in the list payload,
          // so we don't need to wait for the lazy fetch to populate names.
          return (
            <RunListItem
              key={r.id}
              run={r}
              active={r.id === selectedId}
              leadName={r.lead_name || cached?.name}
              leadCompany={r.lead_company || cached?.company}
              onClick={() => selectRun(r.id)}
            />
          );
        })}
      </div>

      {/* Right detail */}
      <div style={{ overflow: 'auto' }}>
        {detailError && detail && (
          <OfflineBanner code={detailError.code} hint={`run ${detail.run.id}`} />
        )}
        <RunDetail
          detail={detail}
          onPause={handlePause}
          onCancel={handleCancel}
          actionState={actionState}
        />
      </div>

      <StartRunModal
        open={startModalOpen}
        onClose={() => setStartModalOpen(false)}
        onRunCreated={handleRunCreated}
      />
    </div>
  );
}
