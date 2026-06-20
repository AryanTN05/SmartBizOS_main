import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { SBButton, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { useLaraUI } from '../../../lib/LaraUIContext.jsx';
import LeadCard from '../components/LeadCard.jsx';
import LeadDrawer from '../components/LeadDrawer.jsx';
import AddLeadModal from '../components/AddLeadModal.jsx';
import ImportCsvModal from '../components/ImportCsvModal.jsx';
import { scoreTone, sourceIcon, tagTone, relTime } from '../lib/helpers.js';
import { toast } from '../lib/toast.jsx';

const STAGES = ['New', 'Contacted', 'Qualified', 'Meeting', 'Proposal', 'Won', 'Lost'];
const STAGE_COLLAPSED_DEFAULT = new Set(['Won', 'Lost']);

// Top-level admin page: leads list/board at /admin/leads.
// Supports Kanban + Table views, optimistic kanban moves, and a detail
// drawer opened on row click.

export default function LeadsList() {
  const navigate = useNavigate();
  const { id: routeId } = useParams();
  const { openDrawer: openLara } = useLaraUI();

  const [leads, setLeads] = useState([]);
  const [totalEstimate, setTotalEstimate] = useState(0);
  const [view, setView] = useState('kanban'); // kanban | table
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [collapsedStages, setCollapsedStages] = useState(STAGE_COLLAPSED_DEFAULT);
  // Bulk selection — only meaningful in table view. Reset whenever the
  // visible list changes so we never act on a stale id set.
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [dragId, setDragId] = useState(null);
  const [dragOverStage, setDragOverStage] = useState(null);

  // Filters + free-text search. Search is debounced 250ms in the input
  // change handler so each keystroke doesn't fire a list request.
  // Filters are URL-persisted so the SDR can bookmark / share / reload
  // without losing context. ?status=hot&intent=positive→ keeps state.
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFiltersLocal] = useState({
    status: searchParams.get('status') || '',
    source: searchParams.get('source') || '',
    min_score: searchParams.get('min_score') || '',
    max_score: searchParams.get('max_score') || '',
    tag: searchParams.get('tag') || '',
    q: searchParams.get('q') || '',
    intent: searchParams.get('intent') || '',
  });
  const setFilters = useCallback((updater) => {
    setFiltersLocal((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      // Mirror to URL — strip empty keys so the URL stays clean.
      const params = new URLSearchParams();
      for (const [k, v] of Object.entries(next)) {
        if (v && String(v).length) params.set(k, String(v));
      }
      setSearchParams(params, { replace: true });
      return next;
    });
  }, [setSearchParams]);
  const [showFilters, setShowFilters] = useState(false);

  const activeFilterCount = useMemo(
    () => Object.values(filters).filter((v) => v && String(v).length).length,
    [filters],
  );

  // ---- fetch -------------------------------------------------------------
  const fetchLeads = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ limit: '50', view });
    for (const [k, v] of Object.entries(filters)) {
      if (v) params.set(k, v);
    }
    try {
      const res = await api.get(`/api/leads?${params.toString()}`);
      setLeads(res.items || []);
      setTotalEstimate(res.total_estimate ?? (res.items || []).length);
    } catch (err) {
      if (err.status === 401) {
        navigate('/admin/login');
        return;
      }
      toast.error(err.message || 'Could not load leads.');
      setLeads([]);
    } finally {
      setLoading(false);
    }
  }, [view, filters, navigate]);

  useEffect(() => {
    fetchLeads();
    // Refetch triggers: Lara emits this when update_lead/create_lead returns;
    // window focus / tab visibility catch the case where the leads page was
    // unmounted at the moment Lara fired the event (e.g. user was on
    // /admin/lara, voice updated a lead, then switched back here).
    const onUpdate = () => fetchLeads();
    const onVisible = () => { if (document.visibilityState === 'visible') fetchLeads(); };
    window.addEventListener('lara:lead_updated', onUpdate);
    window.addEventListener('focus', onUpdate);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('lara:lead_updated', onUpdate);
      window.removeEventListener('focus', onUpdate);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [fetchLeads]);

  // Reset selection when the visible list changes (filter, view switch, refetch).
  useEffect(() => { setSelectedIds(new Set()); }, [view, filters]);

  const toggleSelect = useCallback((id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);
  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => prev.size === leads.length ? new Set() : new Set(leads.map((l) => l.id)));
  }, [leads]);
  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const runBulk = useCallback(async (action, args = {}) => {
    if (selectedIds.size === 0) return;
    const ids = Array.from(selectedIds);
    try {
      const r = await api.post('/api/leads/bulk', { ids, action, args });
      toast.success(`${action.replace('_', ' ')}: ${r.affected} affected${r.skipped ? `, ${r.skipped} skipped` : ''}`);
      clearSelection();
      await fetchLeads();
    } catch (err) {
      toast.error(err?.message || 'Bulk action failed');
    }
  }, [selectedIds, fetchLeads, clearSelection]);

  // ---- derived counts ----------------------------------------------------
  const counts = useMemo(() => {
    const scoreOf = (l) => (typeof l.score === 'object' ? l.score?.value : l.score) ?? 0;
    const hot = leads.filter((l) => (l.tags || []).includes('hot') || scoreOf(l) >= 80).length;
    const warm = leads.filter((l) => (l.tags || []).includes('warm') || (scoreOf(l) >= 60 && scoreOf(l) < 80)).length;
    return { total: totalEstimate || leads.length, hot, warm };
  }, [leads, totalEstimate]);

  // ---- kanban drag/drop --------------------------------------------------
  // Race fix: each drop gets a monotonically increasing seq number. The
  // server response is only applied when it matches the most recent seq —
  // a stale callback from an earlier drop can no longer overwrite the
  // optimistic state of a newer one.
  const dropSeqRef = useRef(0);
  const lastAppliedSeqRef = useRef(new Map()); // lead id → seq
  const onDropToStage = async (stage, e) => {
    e.preventDefault();
    const id = e.dataTransfer.getData('text/plain') || dragId;
    setDragId(null);
    setDragOverStage(null);
    if (!id) return;
    const lead = leads.find((l) => l.id === id);
    if (!lead || lead.status === stage) return;
    const prevStatus = lead.status;
    const seq = ++dropSeqRef.current;
    lastAppliedSeqRef.current.set(id, seq);
    setLeads((ls) => ls.map((l) => (l.id === id ? { ...l, status: stage } : l)));
    try {
      const res = await api.post(`/api/leads/${id}/kanban-move`, { stage });
      // Only apply this server response if no newer drop has fired for
      // the same lead. Otherwise the latest optimistic wins.
      if (lastAppliedSeqRef.current.get(id) !== seq) {
        return;
      }
      if (res?.lead) {
        setLeads((ls) => ls.map((l) => (l.id === id ? res.lead : l)));
      }
    } catch (err) {
      // Same staleness check on the failure path: don't roll back if the
      // user has already started a newer drop on the same lead.
      if (lastAppliedSeqRef.current.get(id) === seq) {
        setLeads((ls) => ls.map((l) => (l.id === id ? { ...l, status: prevStatus } : l)));
        toast.error(err.message || 'Move failed');
      }
    }
  };

  const toggleStageCollapsed = (stage) => {
    setCollapsedStages((set) => {
      const next = new Set(set);
      if (next.has(stage)) next.delete(stage);
      else next.add(stage);
      return next;
    });
  };

  const openLead = (lead) => navigate(`/admin/leads/${lead.id}`);
  const closeLead = () => navigate('/admin/leads');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 60px)' }}>
      {/* Header */}
      <div style={{
        padding: '16px 28px', borderBottom: '1px solid var(--sb-line)',
        display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
      }}>
        <SBChip tone="accent" icon="dot">{counts.total} leads</SBChip>
        <SBChip tone="hot">{counts.hot} hot</SBChip>
        <SBChip tone="warm">{counts.warm} warm</SBChip>

        <div style={{ marginLeft: 12, display: 'flex', gap: 4 }}>
          <SBButton
            variant={view === 'kanban' ? 'secondary' : 'ghost'} size="sm"
            icon="flow" active={view === 'kanban'}
            onClick={() => setView('kanban')}>Kanban</SBButton>
          <SBButton
            variant={view === 'table' ? 'secondary' : 'ghost'} size="sm"
            icon="reports" active={view === 'table'}
            onClick={() => setView('table')}>Table</SBButton>
        </div>

        <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end', paddingRight: 8 }}>
          <input
            value={filters.q}
            onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
            placeholder="Search name, email, company…"
            style={{
              width: 260, padding: '7px 10px',
              background: 'var(--sb-panel)', color: 'var(--sb-fg)',
              border: '1px solid var(--sb-line-2)', fontSize: 12.5,
              fontFamily: 'var(--sb-font)', outline: 'none',
            }}
          />
        </div>

        <SBButton variant="ghost" size="sm" icon="filter"
          active={showFilters || activeFilterCount > 0}
          onClick={() => setShowFilters((v) => !v)}>
          Filters{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ''}
        </SBButton>
        <SBButton variant="secondary" size="sm" icon="spark"
          onClick={() => openLara({ module: 'leads' })}>
          Ask Lara
        </SBButton>
        <SBButton variant="ghost" size="sm" icon="plus"
          onClick={() => setShowImport(true)}>
          Import CSV
        </SBButton>
        <SBButton variant="primary" size="sm" icon="plus"
          onClick={() => setShowAdd(true)}>
          Add lead
        </SBButton>
      </div>

      {/* Quick intent filter chip row — visible at all times so the SDR can
          jump to "show me only positive replies" in one click. */}
      <div style={{
        display: 'flex', gap: 6, padding: '0 20px 10px', flexWrap: 'wrap',
        alignItems: 'center',
      }}>
        <span style={{
          fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
          textTransform: 'uppercase', letterSpacing: '0.08em',
        }}>replies</span>
        <IntentChip active={!filters.intent}
          onClick={() => setFilters((f) => ({ ...f, intent: '' }))}>all</IntentChip>
        {[
          { v: 'positive',     label: 'positive',     tone: 'lime' },
          { v: 'neutral',      label: 'neutral',      tone: 'neutral' },
          { v: 'negative',     label: 'negative',     tone: 'hot' },
          { v: 'wrong_person', label: 'wrong person', tone: 'warm' },
          { v: 'unsubscribe',  label: 'unsub',        tone: 'hot' },
        ].map((t) => (
          <IntentChip key={t.v} tone={t.tone}
            active={filters.intent === t.v}
            onClick={() => setFilters((f) => ({ ...f, intent: f.intent === t.v ? '' : t.v }))}>
            {t.label}
          </IntentChip>
        ))}
      </div>

      {/* Filters panel */}
      {showFilters && (
        <FiltersPanel filters={filters} setFilters={setFilters} onClose={() => setShowFilters(false)} />
      )}

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
        {loading && leads.length === 0 ? (
          <LeadsSkeleton view={view} />
        ) : view === 'kanban' ? (
          <KanbanBoard
            leads={leads}
            collapsed={collapsedStages}
            onToggleCollapse={toggleStageCollapsed}
            onCardClick={openLead}
            onCardDragStart={(l) => setDragId(l.id)}
            onCardDragEnd={() => { setDragId(null); setDragOverStage(null); }}
            dragId={dragId}
            dragOverStage={dragOverStage}
            setDragOverStage={setDragOverStage}
            onDropToStage={onDropToStage}
          />
        ) : (
          <>
            {selectedIds.size > 0 && (
              <BulkActionBar
                count={selectedIds.size}
                onDelete={() => {
                  if (!window.confirm(`Soft-delete ${selectedIds.size} leads? This can be reversed in the DB but not from the UI.`)) return;
                  runBulk('delete');
                }}
                onAddTag={() => {
                  const t = window.prompt('Tag to add (comma-sep for multiple):');
                  if (!t) return;
                  runBulk('add_tags', { tags: t.split(',').map((x) => x.trim()).filter(Boolean) });
                }}
                onSetStage={(status) => runBulk('set_status', { status })}
                onClear={clearSelection}
              />
            )}
            <TableView
              leads={leads}
              onRowClick={openLead}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
              onToggleSelectAll={toggleSelectAll}
            />
          </>
        )}
      </div>

      {/* Import CSV modal */}
      {showImport && (
        <ImportCsvModal
          onClose={() => setShowImport(false)}
          onImported={() => fetchLeads()}
        />
      )}

      {/* Add modal */}
      {showAdd && (
        <AddLeadModal
          onClose={() => setShowAdd(false)}
          onCreated={(lead) => {
            setLeads((ls) => [lead, ...ls]);
            navigate(`/admin/leads/${lead.id}`);
          }}
          onViewExisting={(id) => navigate(`/admin/leads/${id}`)}
        />
      )}

      {/* Drawer */}
      {routeId && (
        <LeadDrawer
          leadId={routeId}
          initialLead={leads.find((l) => l.id === routeId)}
          onClose={closeLead}
          onUpdate={(updated) => setLeads((ls) => ls.map((l) => (l.id === updated.id ? { ...l, ...updated } : l)))}
          onDelete={(id) => setLeads((ls) => ls.filter((l) => l.id !== id))}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Kanban board
// ─────────────────────────────────────────────────────────────────────────────
function KanbanBoard({
  leads, collapsed, onToggleCollapse, onCardClick,
  onCardDragStart, onCardDragEnd, dragId, dragOverStage, setDragOverStage,
  onDropToStage,
}) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: STAGES.map((s) => (collapsed.has(s) ? '52px' : 'minmax(260px, 1fr)')).join(' '),
      gap: 14,
      minWidth: 1000,
    }}>
      {STAGES.map((stage) => {
        const col = leads.filter((l) => (l.status || '').toLowerCase() === stage.toLowerCase());
        const isCollapsed = collapsed.has(stage);
        const isDragTarget = dragOverStage === stage && dragId;
        return (
          <div
            key={stage}
            onDragOver={(e) => {
              e.preventDefault();
              e.dataTransfer.dropEffect = 'move';
              if (dragOverStage !== stage) setDragOverStage(stage);
            }}
            onDragLeave={() => { if (dragOverStage === stage) setDragOverStage(null); }}
            onDrop={(e) => onDropToStage(stage, e)}
            style={{
              minWidth: 0,
              background: isDragTarget ? 'var(--sb-accent-bg)' : 'transparent',
              border: isDragTarget ? '1px dashed var(--sb-accent)' : '1px dashed transparent',
              padding: isDragTarget ? 8 : 0,
              transition: 'background 140ms, border-color 140ms',
            }}
          >
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '0 4px 10px',
            }}>
              <button
                onClick={() => onToggleCollapse(stage)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  background: 'transparent', border: 'none', cursor: 'pointer', padding: 0,
                  color: 'var(--sb-fg-5)',
                }}
                title={isCollapsed ? 'Expand' : 'Collapse'}
              >
                <SBIcon name={isCollapsed ? 'chevronR' : 'chevronD'} size={11} stroke={1.8} />
                {!isCollapsed && <span className="sb-label">{stage}</span>}
                {isCollapsed && (
                  <span className="sb-label" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}>
                    {stage}
                  </span>
                )}
                {!isCollapsed && (
                  <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-4)' }}>
                    {col.length}
                  </span>
                )}
              </button>
              {!isCollapsed && (
                <span style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 10, color: 'var(--sb-fg-5)' }}>
                  {col.length}
                </span>
              )}
            </div>
            {!isCollapsed && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {col.map((l) => (
                  <LeadCard
                    key={l.id}
                    lead={l}
                    onClick={() => onCardClick(l)}
                    onDragStart={onCardDragStart}
                    onDragEnd={onCardDragEnd}
                    dragging={dragId === l.id}
                  />
                ))}
                {col.length === 0 && (
                  <div style={{
                    padding: 12, fontSize: 11.5, color: 'var(--sb-fg-5)',
                    fontFamily: 'var(--sb-font-mono)', fontStyle: 'italic',
                    border: '1px dashed var(--sb-line-2)',
                  }}>
                    drop here
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Table view — dense rows, sortable.
// ─────────────────────────────────────────────────────────────────────────────
function TableView({ leads, onRowClick, selectedIds, onToggleSelect, onToggleSelectAll }) {
  const allSelected = leads.length > 0 && selectedIds && selectedIds.size === leads.length;
  const someSelected = selectedIds && selectedIds.size > 0 && !allSelected;
  const [sort, setSort] = useState({ key: 'score', dir: 'desc' });
  const sorted = useMemo(() => {
    const arr = [...leads];
    arr.sort((a, b) => {
      const scoreOf = (l) => (typeof l.score === 'object' ? l.score?.value : l.score) ?? -1;
      const av = sort.key === 'score' ? scoreOf(a) : (a[sort.key] ?? '');
      const bv = sort.key === 'score' ? scoreOf(b) : (b[sort.key] ?? '');
      if (av < bv) return sort.dir === 'asc' ? -1 : 1;
      if (av > bv) return sort.dir === 'asc' ? 1 : -1;
      return 0;
    });
    return arr;
  }, [leads, sort]);

  const cycleSort = (key) => setSort((s) => s.key === key
    ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
    : { key, dir: 'desc' });

  const headerCell = (label, key, width) => (
    <th
      onClick={() => cycleSort(key)}
      style={{
        textAlign: 'left', padding: '8px 12px', cursor: 'pointer',
        fontSize: 10, fontFamily: 'var(--sb-font-mono)', textTransform: 'uppercase',
        letterSpacing: '0.12em', color: 'var(--sb-fg-5)', fontWeight: 600,
        borderBottom: '1px solid var(--sb-line-2)', width,
        userSelect: 'none', whiteSpace: 'nowrap',
      }}
    >
      {label}
      {sort.key === key && <span style={{ marginLeft: 4 }}>{sort.dir === 'asc' ? '↑' : '↓'}</span>}
    </th>
  );

  return (
    <table style={{
      width: '100%', borderCollapse: 'collapse', background: 'var(--sb-card)',
      border: '1px solid var(--sb-line)',
    }}>
      <thead>
        <tr>
          <th style={{
            padding: '8px 12px', borderBottom: '1px solid var(--sb-line-2)',
            width: 36, textAlign: 'center',
          }}>
            <input
              type="checkbox"
              checked={allSelected}
              ref={(el) => { if (el) el.indeterminate = someSelected; }}
              onChange={onToggleSelectAll}
              onClick={(e) => e.stopPropagation()}
              style={{ cursor: 'pointer' }}
            />
          </th>
          {headerCell('Name', 'name')}
          {headerCell('Company', 'company')}
          {headerCell('Stage', 'status', 120)}
          {headerCell('Score', 'score', 80)}
          {headerCell('Source', 'source', 120)}
          {headerCell('Updated', 'last_activity_at_unix', 110)}
          {headerCell('Owner', 'owner_admin_user_id', 70)}
        </tr>
      </thead>
      <tbody>
        {sorted.length === 0 && (
          <tr><td colSpan={8} style={{ padding: 24, textAlign: 'center', color: 'var(--sb-fg-5)', fontSize: 12.5 }}>
            No leads match these filters.
          </td></tr>
        )}
        {sorted.map((l) => (
          <tr
            key={l.id}
            onClick={() => onRowClick(l)}
            style={{
              cursor: 'pointer', borderBottom: '1px solid var(--sb-line)',
              background: selectedIds?.has(l.id) ? 'var(--sb-accent-bg)' : undefined,
            }}
            onMouseEnter={(e) => { if (!selectedIds?.has(l.id)) e.currentTarget.style.background = 'var(--sb-panel)'; }}
            onMouseLeave={(e) => { if (!selectedIds?.has(l.id)) e.currentTarget.style.background = 'transparent'; }}
          >
            <td
              onClick={(e) => { e.stopPropagation(); onToggleSelect?.(l.id); }}
              style={{ ...cellStyle, textAlign: 'center', cursor: 'pointer', width: 36 }}
            >
              <input
                type="checkbox"
                checked={selectedIds?.has(l.id) || false}
                onChange={() => {}}
                style={{ cursor: 'pointer', pointerEvents: 'none' }}
              />
            </td>
            <td style={cellStyle}>
              <div style={{ fontSize: 12.5, fontWeight: 600 }}>{l.name || '(unnamed)'}</div>
              {l.email && (
                <div style={{ fontSize: 11, color: 'var(--sb-fg-4)', fontFamily: 'var(--sb-font-mono)' }}>
                  {l.email}
                </div>
              )}
            </td>
            <td style={cellStyle}>{l.company || '—'}</td>
            <td style={cellStyle}>
              <span style={{
                fontSize: 10.5, fontFamily: 'var(--sb-font-mono)',
                padding: '2px 8px', background: 'var(--sb-panel)',
                color: 'var(--sb-fg-3)', letterSpacing: '0.05em',
              }}>
                {l.status || '—'}
              </span>
            </td>
            <td style={{ ...cellStyle, fontFamily: 'var(--sb-font-mono)', color: scoreTone(l.score?.value), fontWeight: 700 }}>
              {l.score?.value ?? '—'}
            </td>
            <td style={{ ...cellStyle, fontSize: 11.5, color: 'var(--sb-fg-4)' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: 'var(--sb-font-mono)' }}>
                <SBIcon name={sourceIcon(l.source)} size={11} stroke={1.4} />
                {l.source || '—'}
              </span>
            </td>
            <td style={{ ...cellStyle, fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-4)' }}>
              {relTime(l.last_activity_at_unix || l.updated_at_unix)}
            </td>
            <td style={{ ...cellStyle, fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-4)' }}>
              {l.owner_admin_user_id || '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const cellStyle = {
  padding: '10px 12px', fontSize: 12.5, color: 'var(--sb-fg-2)',
  verticalAlign: 'middle',
};

// ─────────────────────────────────────────────────────────────────────────────
// Filters panel
// ─────────────────────────────────────────────────────────────────────────────
function FiltersPanel({ filters, setFilters, onClose }) {
  const input = { padding: '7px 10px', background: 'var(--sb-panel)', border: '1px solid var(--sb-line-2)', color: 'var(--sb-fg)', fontSize: 12.5, fontFamily: 'var(--sb-font)', outline: 'none' };
  return (
    <div style={{
      padding: '12px 28px', borderBottom: '1px solid var(--sb-line)',
      background: 'var(--sb-bg-2)', display: 'flex', gap: 10, flexWrap: 'wrap',
      alignItems: 'center',
    }}>
      <select value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))} style={input}>
        <option value="">All stages</option>
        {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <select value={filters.source} onChange={(e) => setFilters((f) => ({ ...f, source: e.target.value }))} style={input}>
        <option value="">All sources</option>
        {['manual','lara','hubspot','zoho','sheets','tally','scraper_producthunt','scraper_directory','scraper_review','scraper_linkedin'].map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <input placeholder="Min score" type="number" value={filters.min_score} onChange={(e) => setFilters((f) => ({ ...f, min_score: e.target.value }))} style={{ ...input, width: 110 }} />
      <input placeholder="Max score" type="number" value={filters.max_score} onChange={(e) => setFilters((f) => ({ ...f, max_score: e.target.value }))} style={{ ...input, width: 110 }} />
      <input placeholder="Tag" value={filters.tag} onChange={(e) => setFilters((f) => ({ ...f, tag: e.target.value }))} style={{ ...input, width: 140 }} />
      <div style={{ flex: 1 }} />
      <SBButton variant="ghost" size="xs" onClick={() => setFilters({ status: '', source: '', min_score: '', max_score: '', tag: '', q: '' })}>
        Clear
      </SBButton>
      <SBButton variant="ghost" size="xs" icon="close" onClick={onClose} />
    </div>
  );
}

// Quick filter chip used by the intent row above the kanban/table.
function IntentChip({ active, tone = 'muted', onClick, children }) {
  const TONE = {
    muted:   { bg: 'transparent', border: 'var(--sb-line-2)', fg: 'var(--sb-fg-3)' },
    neutral: { bg: 'transparent', border: 'var(--sb-line-2)', fg: 'var(--sb-fg-3)' },
    lime:    { bg: 'var(--sb-lime-bg)', border: 'var(--sb-lime)', fg: 'var(--sb-lime)' },
    hot:     { bg: 'var(--sb-hot-bg)',  border: 'var(--sb-hot)',  fg: 'var(--sb-hot)' },
    warm:    { bg: 'var(--sb-warm-bg)', border: 'var(--sb-warm)', fg: 'var(--sb-warm)' },
  };
  const t = TONE[tone] || TONE.muted;
  return (
    <button onClick={onClick} style={{
      padding: '4px 10px',
      background: active ? t.bg : 'transparent',
      border: `1px solid ${active ? t.border : 'var(--sb-line-2)'}`,
      color: active ? t.fg : 'var(--sb-fg-4)',
      cursor: 'pointer', fontSize: 11,
      fontFamily: 'var(--sb-font-mono)',
      textTransform: 'uppercase', letterSpacing: '0.06em',
    }}>{children}</button>
  );
}

// Skeleton placeholder during initial load — eliminates the blank flash.
// Mirrors the actual layout (kanban columns vs. table rows) so the swap to
// real content is visually quiet.
function LeadsSkeleton({ view }) {
  const bar = {
    background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
    height: 18, opacity: 0.6, marginBottom: 6,
  };
  if (view === 'kanban') {
    return (
      <div style={{ display: 'flex', gap: 10 }}>
        {[0, 1, 2, 3, 4].map((c) => (
          <div key={c} style={{ flex: 1, minWidth: 220 }}>
            <div style={{ ...bar, height: 12, width: 80, marginBottom: 12 }} />
            {[0, 1, 2].map((i) => (
              <div key={i} style={{
                background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
                padding: '12px 14px', marginBottom: 8, opacity: 0.55,
              }}>
                <div style={{ ...bar, width: '60%', height: 14 }} />
                <div style={{ ...bar, width: '40%', height: 11 }} />
                <div style={{ ...bar, width: '30%', height: 10, marginTop: 4 }} />
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }
  return (
    <div style={{
      background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
    }}>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div key={i} style={{
          padding: '14px 16px', borderBottom: '1px solid var(--sb-line)',
          display: 'grid', gridTemplateColumns: '36px 2fr 1.5fr 1fr 80px 1fr 1fr', gap: 12,
        }}>
          <div style={{ ...bar, height: 14 }} />
          <div>
            <div style={{ ...bar, width: '60%', height: 13 }} />
            <div style={{ ...bar, width: '40%', height: 10 }} />
          </div>
          <div style={{ ...bar, width: '70%' }} />
          <div style={{ ...bar, width: '50%' }} />
          <div style={{ ...bar, width: '40%' }} />
          <div style={{ ...bar, width: '60%' }} />
          <div style={{ ...bar, width: '50%' }} />
        </div>
      ))}
    </div>
  );
}

// Sticky action bar shown above the table when one or more leads are selected.
// Keep the action set tight — delete + tag + stage cover 90% of bulk SDR work.
function BulkActionBar({ count, onDelete, onAddTag, onSetStage, onClear }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '10px 14px', marginBottom: 10,
      background: 'var(--sb-accent-bg)', border: '1px solid var(--sb-accent)',
      position: 'sticky', top: 0, zIndex: 5,
    }}>
      <SBChip tone="accent" icon="check">{count} selected</SBChip>
      <div style={{ flex: 1 }} />
      <SBButton variant="ghost" size="xs" icon="plus" onClick={onAddTag}>Add tag</SBButton>
      <select
        defaultValue=""
        onChange={(e) => { if (e.target.value) { onSetStage(e.target.value); e.target.value = ''; } }}
        style={{
          padding: '5px 8px', background: 'var(--sb-panel)',
          border: '1px solid var(--sb-line-2)', color: 'var(--sb-fg)',
          fontSize: 11.5, fontFamily: 'var(--sb-font)', outline: 'none',
        }}
      >
        <option value="">Set stage…</option>
        {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <SBButton variant="danger" size="xs" icon="close" onClick={onDelete}>Delete</SBButton>
      <SBButton variant="ghost" size="xs" onClick={onClear}>Clear</SBButton>
    </div>
  );
}
