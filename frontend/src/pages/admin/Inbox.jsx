import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBCard, SBChip, SBIcon, SBSkeleton } from '../../components/primitives';
import api from '../../lib/api.js';
import { toast } from '../../modules/leads/lib/toast.jsx';
import StartRunModal from '../../modules/automations/components/StartRunModal.jsx';
import EmptyStateDiagnostic from '../../modules/inbox/components/EmptyStateDiagnostic.jsx';

// /admin/inbox — actionable triage view for enriched scraper captures.
//
// Triage at volume needs three things the v1 of this page didn't have:
//   1. Full context inline so you can decide without navigating away
//      (rubric breakdown, tech, Hunter intel, page snippet).
//   2. Keyboard shortcuts (j/k navigate, c convert, x dismiss, e re-enrich,
//      v convert+sequence, ? help). A real SDR cleans 50 captures via
//      keys, not by mousing across a 1080p screen 50 times.
//   3. Undoable bulk actions — dismissing 40 rows is too easy to misclick.
//      We post the action, then surface a 6-second toast with an "Undo"
//      button that flips them back to pending via /scrapers/results/bulk
//      action=restore.

const TIERS = [
  { key: 'hot',     label: 'HOT',     min: 80, max: 100, tone: 'hot',   advice: 'Convert + start sequence.' },
  { key: 'warm',    label: 'WARM',    min: 60, max: 79,  tone: 'warm',  advice: 'Promote and triage manually.' },
  { key: 'nurture', label: 'NURTURE', min: 40, max: 59,  tone: 'cool',  advice: 'Lower fit. Promote selectively.' },
  { key: 'skip',    label: 'SKIP',    min: 0,  max: 39,  tone: 'muted', advice: 'Disqualified. Safe to bulk-dismiss.' },
];

function tierFor(score) {
  if (score == null) return 'nurture';
  for (const t of TIERS) {
    if (score >= t.min && score <= t.max) return t.key;
  }
  return 'nurture';
}

const RUBRIC_LABELS = {
  segment_fit:    'Segment fit',
  company_size:   'Company size',
  revenue_stage:  'Revenue stage',
  revops_pain:    'RevOps pain',
  buying_trigger: 'Buying trigger',
};
const RUBRIC_MAX = {
  segment_fit: 25, company_size: 20, revenue_stage: 20, revops_pain: 20, buying_trigger: 15,
};

export default function Inbox() {
  const navigate = useNavigate();
  const [items, setItems] = useState(null);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(200);  // honest default — bumps on demand
  const [busy, setBusy] = useState(false);
  const [collapsed, setCollapsed] = useState(() => new Set(['nurture', 'skip']));
  const [selected, setSelected] = useState(() => new Set());
  const [expandedId, setExpandedId] = useState(null);
  const [tierFilter, setTierFilter] = useState(null); // null = all
  const [sourceFilter, setSourceFilter] = useState(null);
  const [showHelp, setShowHelp] = useState(false);
  const [focusedId, setFocusedId] = useState(null);
  // Convert+Sequence modal seed.
  const [pendingSeqLeadId, setPendingSeqLeadId] = useState(null);
  const rowRefs = useRef({});

  const fetchItems = useCallback(async (opts = {}) => {
    const limit = opts.limit ?? pageSize;
    try {
      const r = await api.get(`/api/scrapers/results?status=pending&limit=${limit}`, { fresh: true });
      setItems(r?.items || []);
      setTotal(r?.total ?? (r?.items || []).length);
    } catch (err) {
      if (err?.status === 401) { window.location.href = '/admin/login'; return; }
      toast.error(err?.message || 'Could not load inbox.');
      setItems([]);
      setTotal(0);
    }
  }, [pageSize]);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  const loadMore = useCallback(async () => {
    const next = Math.min(500, pageSize + 200);
    setPageSize(next);
    await fetchItems({ limit: next });
  }, [pageSize, fetchItems]);

  // ---- derived ----------------------------------------------------------

  const enriched = useMemo(() => {
    return (items || []).map((it) => {
      const score = (it.raw?.enrichment?.score) ?? it.relevance_score ?? null;
      return { ...it, _score: score, _tier: tierFor(score) };
    });
  }, [items]);

  const sourceTypes = useMemo(() => {
    const s = new Set();
    for (const it of enriched) s.add(it.source_type);
    return Array.from(s).sort();
  }, [enriched]);

  const filtered = useMemo(() => {
    return enriched.filter((it) => {
      if (tierFilter && it._tier !== tierFilter) return false;
      if (sourceFilter && it.source_type !== sourceFilter) return false;
      return true;
    });
  }, [enriched, tierFilter, sourceFilter]);

  const grouped = useMemo(() => {
    const buckets = { hot: [], warm: [], nurture: [], skip: [] };
    for (const it of filtered) buckets[it._tier].push(it);
    for (const k of Object.keys(buckets)) {
      buckets[k].sort((a, b) => (b._score ?? 0) - (a._score ?? 0));
    }
    return buckets;
  }, [filtered]);

  // Tier counts always reflect the FULL set (so the chip distribution
  // doesn't lie when a filter is active).
  const tierCounts = useMemo(() => {
    const c = { hot: 0, warm: 0, nurture: 0, skip: 0 };
    for (const it of enriched) c[it._tier]++;
    return c;
  }, [enriched]);

  // Visible-row order for keyboard navigation. Includes only rows that
  // pass the active filter and live in a non-collapsed tier.
  const visibleRows = useMemo(() => {
    const out = [];
    for (const tier of TIERS) {
      if (collapsed.has(tier.key)) continue;
      for (const r of grouped[tier.key]) out.push(r);
    }
    return out;
  }, [grouped, collapsed]);

  // ---- selection / expansion -------------------------------------------

  const toggleSelect = useCallback((id) => setSelected((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  }), []);

  const selectTier = (tierKey) => {
    setSelected((s) => new Set([...s, ...grouped[tierKey].map((r) => r.id)]));
  };
  const clearSelection = () => setSelected(new Set());

  const toggleCollapse = (k) => setCollapsed((s) => {
    const n = new Set(s);
    n.has(k) ? n.delete(k) : n.add(k);
    return n;
  });

  const toggleExpand = useCallback((id) => {
    setExpandedId((cur) => cur === id ? null : id);
  }, []);

  // ---- bulk actions -----------------------------------------------------

  // Run bulk LLM opener-drafting for a list of new lead ids. Toast updates
  // with the per-batch result. Designed to be chained after a bulk-convert
  // so the user can go from "20 captures" → "20 leads with openers ready"
  // in two clicks.
  const draftOpenersForLeadIds = useCallback(async (lead_ids) => {
    if (!lead_ids || lead_ids.length === 0) return;
    try {
      toast.info(`Drafting ${lead_ids.length} openers…`);
      const r = await api.post('/api/leads/bulk/opening-lines', {
        lead_ids, force: false,
      });
      const s = r?.summary || {};
      const parts = [];
      if (s.generated) parts.push(`${s.generated} drafted`);
      if (s.cached)    parts.push(`${s.cached} cached`);
      if (s.skipped_no_signal) parts.push(`${s.skipped_no_signal} skipped (no signal)`);
      if (s.errors)    parts.push(`${s.errors} errored`);
      const summary = parts.length ? parts.join(' · ') : 'No openers drafted';
      toast.success(summary, {
        duration: 6500,
        action: { label: 'View leads', onClick: () => navigate('/admin/leads') },
      });
    } catch (err) {
      toast.error(err?.message || 'Bulk drafting failed');
    }
  }, [navigate]);

  const runBulk = useCallback(async (action, ids, { showUndo = false } = {}) => {
    if (!ids || ids.length === 0) return;
    setBusy(true);
    try {
      const r = await api.post('/api/scrapers/results/bulk', { ids, action });
      const verb = { convert: 'Converted', dismiss: 'Dismissed', restore: 'Restored' }[action];
      const summary = `${verb} ${r.affected}${r.skipped ? ` · skipped ${r.skipped}` : ''}`;
      // Undo only on dismiss — convert mints leads we'd have to delete to
      // undo, which is more complex. Skip undo for tiny actions (<3 rows).
      if (showUndo && action === 'dismiss' && r.affected >= 3) {
        toast.success(summary, {
          duration: 6500,
          action: {
            label: 'Undo',
            onClick: async () => {
              try {
                await api.post('/api/scrapers/results/bulk', { ids, action: 'restore' });
                toast.info('Restored');
                await fetchItems();
              } catch (err) {
                toast.error(err?.message || 'Restore failed');
              }
            },
          },
        });
      } else if (action === 'convert' && r.affected > 0) {
        // Bulk-convert silently empties the inbox — make it obvious where
        // those rows went and offer to draft openers in one click. The
        // wedge stays a daily workflow when this chain is one button.
        const newIds = r?.new_lead_ids || [];
        toast.success(`${summary} · added to /admin/leads`, {
          duration: 9000,
          action: newIds.length ? {
            label: `Draft ${newIds.length} openers`,
            onClick: () => draftOpenersForLeadIds(newIds),
          } : {
            label: 'View leads',
            onClick: () => navigate('/admin/leads'),
          },
        });
      } else {
        toast.success(summary);
      }
      clearSelection();
      await fetchItems();
      return r;
    } catch (err) {
      toast.error(err?.message || 'Bulk action failed');
    } finally {
      setBusy(false);
    }
  }, [fetchItems, draftOpenersForLeadIds, navigate]);

  // Single-row actions piggyback on the bulk endpoint with one id so we
  // get the same FOR UPDATE locking + uniform response shape.
  const onConvert = useCallback((id) => runBulk('convert', [id]), [runBulk]);
  const onDismiss = useCallback((id) => runBulk('dismiss', [id], { showUndo: true }), [runBulk]);

  const onReEnrich = useCallback(async (id) => {
    setBusy(true);
    try {
      await api.post(`/api/scrapers/results/${id}/enrich`);
      toast.info('Re-enriching…');
      // Lightweight refetch in 3s — server-side enrich is sync but page
      // fetcher + LLM round-trip can take 10-15s. Tell the user.
      setTimeout(() => fetchItems(), 3500);
    } catch (err) {
      toast.error(err?.message || 'Re-enrich failed');
    } finally {
      setBusy(false);
    }
  }, [fetchItems]);

  // Convert + open StartRunModal pre-seeded with the new lead. The modal
  // mounts at the page level so its own state machine handles the
  // template picker + run creation.
  const onConvertAndSequence = useCallback(async (id) => {
    setBusy(true);
    try {
      const r = await api.post('/api/scrapers/results/bulk', { ids: [id], action: 'convert' });
      const newLeadId = r?.new_lead_ids?.[0];
      if (!newLeadId) throw new Error('Convert returned no lead id');
      toast.success('Converted — pick a template');
      setPendingSeqLeadId(newLeadId);
      await fetchItems();
    } catch (err) {
      toast.error(err?.message || 'Convert + sequence failed');
    } finally {
      setBusy(false);
    }
  }, [fetchItems]);

  // ---- keyboard ---------------------------------------------------------

  // Keep latest dependencies inside refs so the keydown handler doesn't
  // tear down + rebind on every render (which would also drop in-flight
  // listeners).
  const stateRef = useRef({});
  stateRef.current = {
    visibleRows, focusedId, expandedId, selected,
    onConvert, onDismiss, onReEnrich, onConvertAndSequence,
    setFocusedId, setExpandedId, toggleSelect, setShowHelp,
  };

  useEffect(() => {
    const onKey = (e) => {
      // Ignore when typing into an input/textarea/contenteditable.
      const target = e.target;
      const tag = target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const s = stateRef.current;
      const rows = s.visibleRows;
      if (!rows.length) return;
      const idx = rows.findIndex((r) => r.id === s.focusedId);
      const cur = idx >= 0 ? rows[idx] : null;

      const focusByIndex = (i) => {
        const next = rows[Math.max(0, Math.min(rows.length - 1, i))];
        if (!next) return;
        s.setFocusedId(next.id);
        const el = rowRefs.current[next.id];
        if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      };

      switch (e.key) {
        case 'j': focusByIndex(idx < 0 ? 0 : idx + 1); e.preventDefault(); break;
        case 'k': focusByIndex(idx < 0 ? 0 : idx - 1); e.preventDefault(); break;
        case 'Enter':
        case ' ':
          if (cur) { s.setExpandedId((x) => x === cur.id ? null : cur.id); e.preventDefault(); }
          break;
        case 'c':
          if (cur && !cur.converted_lead_id) { s.onConvert(cur.id); e.preventDefault(); }
          break;
        case 'v':
          if (cur && !cur.converted_lead_id) { s.onConvertAndSequence(cur.id); e.preventDefault(); }
          break;
        case 'x':
          if (cur && !cur.converted_lead_id) { s.onDismiss(cur.id); e.preventDefault(); }
          break;
        case 'e':
          if (cur) { s.onReEnrich(cur.id); e.preventDefault(); }
          break;
        case 's':
          if (cur) { s.toggleSelect(cur.id); e.preventDefault(); }
          break;
        case '?':
          s.setShowHelp((h) => !h); e.preventDefault();
          break;
        case 'Escape':
          s.setShowHelp(false); s.setExpandedId(null); e.preventDefault();
          break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Default focus to the first visible row once data lands.
  useEffect(() => {
    if (focusedId == null && visibleRows.length > 0) {
      setFocusedId(visibleRows[0].id);
    }
    if (focusedId && !visibleRows.find((r) => r.id === focusedId)) {
      setFocusedId(visibleRows[0]?.id || null);
    }
  }, [visibleRows, focusedId]);

  // ---- empty / loading states ------------------------------------------

  if (items === null) {
    return (
      <div style={{ padding: '28px 32px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
          <SBSkeleton variant="row" h={20} w={140} />
          <SBSkeleton variant="row" h={32} w={300} />
        </div>
        {/* Tier-group skeletons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {Array.from({ length: 4 }).map((_, ti) => (
            <div key={ti}>
              <SBSkeleton variant="row" h={28} w="40%" style={{ marginBottom: 6, opacity: Math.max(0.3, 1 - ti * 0.15) }} />
              <SBSkeleton variant="card" h={80} style={{ opacity: Math.max(0.3, 1 - ti * 0.15) }} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return <EmptyStateDiagnostic />;
  }

  // ---- render -----------------------------------------------------------

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1100 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 24, marginBottom: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 6 }}>Triage</div>
          <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 26, fontWeight: 600, margin: 0, letterSpacing: '-0.02em' }}>
            Triage the queue.
          </h1>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          <SBButton
            variant="primary" size="sm" icon="bolt"
            disabled={busy || tierCounts.hot === 0}
            onClick={() => runBulk('convert', enriched.filter((r) => r._tier === 'hot').map((r) => r.id))}
          >
            Convert all HOT ({tierCounts.hot})
          </SBButton>
          <SBButton
            variant="ghost" size="sm" icon="close"
            disabled={busy || tierCounts.skip === 0}
            onClick={() => runBulk('dismiss', enriched.filter((r) => r._tier === 'skip').map((r) => r.id), { showUndo: true })}
          >
            Dismiss all SKIP ({tierCounts.skip})
          </SBButton>
          <SBButton variant="ghost" size="sm" onClick={() => setShowHelp((h) => !h)}>?</SBButton>
        </div>
      </div>

      {/* Tier-distribution chip row */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <FilterChip
          tone="accent" active={!tierFilter}
          onClick={() => setTierFilter(null)}
        >
          All · {enriched.length}
        </FilterChip>
        {TIERS.map((t) => (
          <FilterChip
            key={t.key} tone={t.tone}
            active={tierFilter === t.key}
            onClick={() => setTierFilter((cur) => cur === t.key ? null : t.key)}
          >
            {t.label} · {tierCounts[t.key]}
          </FilterChip>
        ))}
        {sourceTypes.length > 1 && (
          <>
            <div style={{ width: 1, height: 16, background: 'var(--sb-line-2)', margin: '0 4px' }} />
            <FilterChip
              tone="muted" active={!sourceFilter}
              onClick={() => setSourceFilter(null)}
            >all sources</FilterChip>
            {sourceTypes.map((s) => (
              <FilterChip
                key={s} tone="muted"
                active={sourceFilter === s}
                onClick={() => setSourceFilter((cur) => cur === s ? null : s)}
              >{s}</FilterChip>
            ))}
          </>
        )}
        {total > enriched.length && (
          <>
            <div style={{ flex: 1 }} />
            <span style={{
              fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
            }}>
              showing {enriched.length} of {total}
            </span>
            {pageSize < 500 && (
              <SBButton variant="ghost" size="xs" icon="arrow"
                onClick={loadMore} disabled={busy}>
                Load more
              </SBButton>
            )}
          </>
        )}
      </div>

      {/* Multi-select bar */}
      {selected.size > 0 && (
        <div style={{
          position: 'sticky', top: 0, zIndex: 5,
          padding: '10px 14px', marginBottom: 12,
          background: 'var(--sb-accent-bg)', border: '1px solid var(--sb-accent)',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <SBChip tone="accent" icon="check">{selected.size} selected</SBChip>
          <div style={{ flex: 1 }} />
          <SBButton variant="primary" size="xs" icon="check"
            disabled={busy} onClick={() => runBulk('convert', Array.from(selected))}>
            Convert
          </SBButton>
          <SBButton variant="danger" size="xs" icon="close"
            disabled={busy} onClick={() => runBulk('dismiss', Array.from(selected), { showUndo: true })}>
            Dismiss
          </SBButton>
          <SBButton variant="ghost" size="xs" onClick={clearSelection}>Clear</SBButton>
        </div>
      )}

      {/* Tier groups */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {TIERS.filter((t) => !tierFilter || tierFilter === t.key).map((tier) => (
          <TierGroup
            key={tier.key}
            tier={tier}
            rows={grouped[tier.key]}
            collapsed={collapsed.has(tier.key)}
            onToggle={() => toggleCollapse(tier.key)}
            selected={selected}
            onToggleSelect={toggleSelect}
            onSelectAll={() => selectTier(tier.key)}
            expandedId={expandedId}
            onToggleExpand={toggleExpand}
            focusedId={focusedId}
            onConvert={onConvert}
            onConvertAndSequence={onConvertAndSequence}
            onDismiss={onDismiss}
            onReEnrich={onReEnrich}
            onOpenLead={(leadId) => navigate(`/admin/leads/${leadId}`)}
            busy={busy}
            rowRefs={rowRefs}
          />
        ))}
      </div>

      {/* Help overlay */}
      {showHelp && <ShortcutsOverlay onClose={() => setShowHelp(false)} />}

      {/* Convert + Sequence modal */}
      <StartRunModal
        open={!!pendingSeqLeadId}
        onClose={() => setPendingSeqLeadId(null)}
        leadId={pendingSeqLeadId}
        onRunCreated={() => {
          setPendingSeqLeadId(null);
          toast.success('Sequence started');
        }}
      />
    </div>
  );
}

function FilterChip({ children, tone, active, onClick }) {
  const toneFg = {
    accent: 'var(--sb-accent)',
    hot:    'var(--sb-hot)',
    warm:   'var(--sb-warm)',
    cool:   'var(--sb-cool)',
    muted:  'var(--sb-fg-4)',
  }[tone] || 'var(--sb-fg-3)';
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? toneFg + '22' : 'transparent',
        border: `1px solid ${active ? toneFg : 'var(--sb-line-2)'}`,
        color: active ? toneFg : 'var(--sb-fg-3)',
        padding: '5px 10px', cursor: 'pointer',
        fontSize: 11, fontFamily: 'var(--sb-font-mono)',
        textTransform: 'uppercase', letterSpacing: '0.08em',
      }}
    >{children}</button>
  );
}

function TierGroup({
  tier, rows, collapsed, onToggle, selected, onToggleSelect, onSelectAll,
  expandedId, onToggleExpand, focusedId,
  onConvert, onConvertAndSequence, onDismiss, onReEnrich, onOpenLead,
  busy, rowRefs,
}) {
  const count = rows.length;
  const allSelected = count > 0 && rows.every((r) => selected.has(r.id));
  return (
    <SBCard style={{ padding: 0 }}>
      <div
        onClick={onToggle}
        style={{
          padding: '12px 18px', display: 'flex', alignItems: 'center', gap: 12,
          cursor: 'pointer', borderBottom: collapsed ? 'none' : '1px solid var(--sb-line)',
          userSelect: 'none',
        }}
      >
        <SBIcon name={collapsed ? 'chevronR' : 'chevronD'} size={12} />
        <SBChip tone={tier.tone}>{tier.label}</SBChip>
        <span style={{ fontSize: 12, color: 'var(--sb-fg-4)' }}>
          {count} {count === 1 ? 'capture' : 'captures'}
        </span>
        <span style={{ fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
          {tier.min}–{tier.max}
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 11.5, color: 'var(--sb-fg-5)' }}>{tier.advice}</span>
        {count > 0 && !collapsed && (
          <SBButton variant="ghost" size="xs"
            onClick={(e) => { e.stopPropagation(); onSelectAll(); }}>
            {allSelected ? 'deselect' : 'select all'}
          </SBButton>
        )}
      </div>
      {!collapsed && count === 0 && (
        <div style={{
          padding: '20px 18px', fontSize: 12, color: 'var(--sb-fg-5)', fontStyle: 'italic',
        }}>
          Nothing in this tier yet.
        </div>
      )}
      {!collapsed && rows.map((r) => (
        <CaptureRow
          key={r.id}
          row={r}
          isSelected={selected.has(r.id)}
          isExpanded={expandedId === r.id}
          isFocused={focusedId === r.id}
          rowRef={(el) => { if (el) rowRefs.current[r.id] = el; else delete rowRefs.current[r.id]; }}
          onToggleSelect={() => onToggleSelect(r.id)}
          onToggleExpand={() => onToggleExpand(r.id)}
          onConvert={() => onConvert(r.id)}
          onConvertAndSequence={() => onConvertAndSequence(r.id)}
          onDismiss={() => onDismiss(r.id)}
          onReEnrich={() => onReEnrich(r.id)}
          onOpenLead={onOpenLead}
          busy={busy}
        />
      ))}
    </SBCard>
  );
}

function CaptureRow({
  row, isSelected, isExpanded, isFocused, rowRef,
  onToggleSelect, onToggleExpand,
  onConvert, onConvertAndSequence, onDismiss, onReEnrich, onOpenLead, busy,
}) {
  const enrich = row.raw?.enrichment || {};
  const reason = enrich.reason || row.raw?.summary;
  const tech = enrich.tech || [];
  const isHot = row._tier === 'hot';
  const isWarm = row._tier === 'warm';

  return (
    <div
      ref={rowRef}
      style={{
        borderBottom: '1px solid var(--sb-line)',
        background: isSelected ? 'var(--sb-accent-bg)'
                   : isFocused ? 'var(--sb-panel)'
                   : 'transparent',
        borderLeft: isFocused ? '2px solid var(--sb-accent)' : '2px solid transparent',
      }}
    >
      <div
        onClick={onToggleExpand}
        style={{
          padding: '14px 18px', display: 'grid',
          gridTemplateColumns: '24px 70px 1fr auto', gap: 14,
          cursor: 'pointer',
        }}
      >
        <input
          type="checkbox" checked={isSelected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
          style={{ marginTop: 4, cursor: 'pointer' }}
        />
        <div style={{ textAlign: 'right' }}>
          <div style={{
            fontFamily: 'var(--sb-font-mono)', fontSize: 22, fontWeight: 500,
            color: isHot ? 'var(--sb-hot)' : isWarm ? 'var(--sb-warm)' : 'var(--sb-fg-4)',
            lineHeight: 1,
          }}>{row._score ?? '—'}</div>
          <div style={{ fontSize: 9.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', marginTop: 4, letterSpacing: '0.06em' }}>
            /100
          </div>
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 2 }}>
            {row.name || row.company || 'Untitled'}
            {row.company && row.name && (
              <span style={{ color: 'var(--sb-fg-5)', fontWeight: 400, marginLeft: 8 }}>
                · {row.company}
              </span>
            )}
          </div>
          {row.url && (
            <a
              href={row.url} target="_blank" rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              style={{
                fontSize: 11.5, color: 'var(--sb-accent)', fontFamily: 'var(--sb-font-mono)',
                textDecoration: 'none', wordBreak: 'break-all',
              }}
            >{row.url}</a>
          )}
          {reason && (
            <div style={{ fontSize: 12, color: 'var(--sb-fg-3)', marginTop: 6, lineHeight: 1.55 }}>
              {reason}
            </div>
          )}
          <div style={{
            marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap',
            fontSize: 10.5, fontFamily: 'var(--sb-font-mono)',
          }}>
            <SBChip tone="muted">{row.source_type}</SBChip>
            {tech.slice(0, 5).map((t) => <SBChip key={t} tone="cool">{t}</SBChip>)}
          </div>
        </div>
        <div
          onClick={(e) => e.stopPropagation()}
          style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}
        >
          {row.converted_lead_id ? (
            <SBButton variant="ghost" size="xs" iconRight="arrow"
              onClick={() => onOpenLead(row.converted_lead_id)}>
              Open lead
            </SBButton>
          ) : (
            <>
              {(isHot || isWarm) && (
                <SBButton variant="primary" size="xs" icon="bolt"
                  disabled={busy} onClick={onConvertAndSequence}>
                  Convert + sequence
                </SBButton>
              )}
              <SBButton variant={isHot || isWarm ? 'ghost' : 'primary'} size="xs" icon="check"
                disabled={busy} onClick={onConvert}>
                Convert
              </SBButton>
              <SBButton variant="ghost" size="xs" icon="close"
                disabled={busy} onClick={onDismiss}>
                Dismiss
              </SBButton>
            </>
          )}
        </div>
      </div>

      {/* Expanded details */}
      {isExpanded && <ExpandedDetails row={row} onReEnrich={onReEnrich} busy={busy} />}
    </div>
  );
}

function ExpandedDetails({ row, onReEnrich, busy }) {
  const e = row.raw?.enrichment || {};
  const dim = e.dimensions || {};
  const hunter = e.hunter || {};
  const verify = e.email_verification || {};
  const meta = e.page_meta || {};
  const desc = e.description || row.raw?.summary;
  const tech = e.tech || [];
  const emails = e.emails || [];

  const hasRubric = Object.keys(dim).length > 0;
  const hasHunter = !!(hunter.organization || hunter.industry || hunter.headcount || hunter.country);

  return (
    <div style={{
      padding: '14px 20px 18px 110px',
      background: 'var(--sb-card-2)',
      borderTop: '1px solid var(--sb-line)',
      display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 24,
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
        {desc && (
          <Section title="Page snippet">
            <div style={{ fontSize: 12.5, color: 'var(--sb-fg-2)', lineHeight: 1.55 }}>
              {desc}
            </div>
          </Section>
        )}
        {hasRubric && (
          <Section title="Rubric breakdown">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {Object.entries(RUBRIC_LABELS).map(([k, label]) => {
                const v = dim[k];
                const max = RUBRIC_MAX[k];
                const pct = (v != null && max) ? Math.max(0, Math.min(100, (v / max) * 100)) : 0;
                return (
                  <div key={k} style={{ display: 'grid', gridTemplateColumns: '110px 1fr 50px', gap: 10, alignItems: 'center', fontSize: 11.5 }}>
                    <span style={{ color: 'var(--sb-fg-4)' }}>{label}</span>
                    <div style={{ height: 6, background: 'var(--sb-panel)', position: 'relative' }}>
                      <div style={{
                        position: 'absolute', inset: 0, width: `${pct}%`,
                        background: pct >= 70 ? 'var(--sb-accent)' : pct >= 40 ? 'var(--sb-warm)' : 'var(--sb-fg-5)',
                      }} />
                    </div>
                    <span style={{ fontFamily: 'var(--sb-font-mono)', textAlign: 'right', color: 'var(--sb-fg-3)' }}>
                      {v ?? '—'}/{max}
                    </span>
                  </div>
                );
              })}
            </div>
          </Section>
        )}
        {tech.length > 0 && (
          <Section title="Tech detected">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {tech.slice(0, 14).map((t) => <SBChip key={t} tone="cool">{t}</SBChip>)}
            </div>
          </Section>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
        {hasHunter && (
          <Section title="Hunter intel">
            <KV k="company"  v={hunter.organization || '—'} />
            {hunter.industry && <KV k="industry" v={hunter.industry} />}
            {hunter.headcount && <KV k="headcount" v={hunter.headcount} />}
            {hunter.country && <KV k="country" v={hunter.country} />}
          </Section>
        )}
        {verify.result && (
          <Section title="Email deliverability">
            <SBChip tone={verify.result === 'deliverable' ? 'hot' : verify.result === 'risky' ? 'warm' : 'muted'}>
              {verify.result}
            </SBChip>
            {verify.score != null && (
              <span style={{ marginLeft: 8, fontSize: 11.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
                score {verify.score}
              </span>
            )}
          </Section>
        )}
        {emails.length > 0 && (
          <Section title={`Captured emails (${emails.length})`}>
            {emails.slice(0, 4).map((em) => (
              <div key={em} style={{ fontSize: 11.5, color: 'var(--sb-fg-3)', fontFamily: 'var(--sb-font-mono)' }}>{em}</div>
            ))}
          </Section>
        )}
        {(meta.title || e.fetcher) && (
          <Section title="Trace">
            {meta.title && <KV k="title" v={meta.title} />}
            {e.fetcher && <KV k="fetcher" v={e.fetcher} />}
            {e.domain && <KV k="domain" v={e.domain} />}
          </Section>
        )}
        <div style={{ display: 'flex', gap: 6 }}>
          <SBButton variant="ghost" size="xs" icon="spark" disabled={busy} onClick={onReEnrich}>
            Re-enrich
          </SBButton>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div style={{
        fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
        textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6,
      }}>{title}</div>
      {children}
    </div>
  );
}

function KV({ k, v }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', gap: 10, fontSize: 11.5, marginBottom: 4 }}>
      <span style={{ color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>{k}</span>
      <span style={{ color: 'var(--sb-fg-2)' }}>{v}</span>
    </div>
  );
}

function ShortcutsOverlay({ onClose }) {
  const rows = [
    ['j / k',     'Move focus down / up'],
    ['Enter, Space', 'Toggle expanded details'],
    ['c',         'Convert focused capture'],
    ['v',         'Convert + start sequence'],
    ['x',         'Dismiss focused capture'],
    ['e',         'Re-enrich focused capture'],
    ['s',         'Toggle row selection'],
    ['Esc',       'Close panel / overlay'],
    ['?',         'Toggle this help'],
  ];
  return (
    <>
      <div onClick={onClose} style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 80,
      }} />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        width: 460, maxWidth: '92vw', zIndex: 85,
        background: 'var(--sb-bg)', border: '1px solid var(--sb-line-2)',
        padding: 24,
      }}>
        <div className="sb-label" style={{ marginBottom: 14, color: 'var(--sb-accent)' }}>Keyboard shortcuts</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {rows.map(([key, desc]) => (
            <div key={key} style={{
              display: 'grid', gridTemplateColumns: '120px 1fr', gap: 16, fontSize: 12.5,
            }}>
              <kbd style={{
                fontFamily: 'var(--sb-font-mono)', fontSize: 11,
                padding: '3px 8px', background: 'var(--sb-panel)',
                border: '1px solid var(--sb-line-2)', color: 'var(--sb-accent)',
                width: 'fit-content',
              }}>{key}</kbd>
              <span style={{ color: 'var(--sb-fg-3)' }}>{desc}</span>
            </div>
          ))}
        </div>
        <div style={{
          marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--sb-line)',
          fontSize: 11.5, color: 'var(--sb-fg-5)', textAlign: 'right',
        }}>
          press <kbd style={{ padding: '1px 6px', background: 'var(--sb-panel)', border: '1px solid var(--sb-line-2)' }}>?</kbd> to close
        </div>
      </div>
    </>
  );
}
