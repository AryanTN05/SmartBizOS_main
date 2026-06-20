import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../../lib/api.js';
import { SBButton, SBCard, SBChip } from '../../../components/primitives';
import {
  formatPeriodRange,
  pickStat,
  fmtInt,
  fmtPercent,
  narrativeExcerpt,
  isAuthError,
} from '../lib/format.js';

const KINDS = ['', 'weekly', 'daily', 'monthly', 'custom'];

// Turn a yyyy-mm-dd date input into Unix seconds UTC midnight.
function dateToUnix(s) {
  if (!s) return null;
  const d = new Date(`${s}T00:00:00Z`);
  const n = Math.floor(d.getTime() / 1000);
  return Number.isFinite(n) ? n : null;
}
function currentWeekRange() {
  const now = Math.floor(Date.now() / 1000);
  // Align end to next Monday 00:00 UTC.
  const d = new Date(now * 1000);
  const dow = d.getUTCDay(); // 0=Sun..6=Sat; "week ending Sunday" -> end = next Monday
  const daysToMon = (8 - dow) % 7 || 7;
  const endD = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + daysToMon));
  const end = Math.floor(endD.getTime() / 1000);
  const start = end - 7 * 24 * 3600;
  return { start, end };
}

export default function ReportsList() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [kind, setKind] = useState('');
  const [startAfter, setStartAfter] = useState('');
  const [endBefore, setEndBefore] = useState('');
  const [showGen, setShowGen] = useState(false);

  const fetchList = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const params = new URLSearchParams({ limit: '25' });
    if (kind) params.set('kind', kind);
    const sa = dateToUnix(startAfter);
    const eb = dateToUnix(endBefore);
    if (sa) params.set('period_start_after', String(sa));
    if (eb) params.set('period_end_before', String(eb));
    try {
      const r = await api.get(`/api/reports?${params.toString()}`);
      setItems(Array.isArray(r?.items) ? r.items : []);
    } catch (e) {
      if (isAuthError(e)) {
        navigate('/admin/login', { replace: true });
        return;
      }
      setItems([]);
      setErr(e);
    } finally {
      setLoading(false);
    }
  }, [kind, startAfter, endBefore, navigate]);

  useEffect(() => { fetchList(); }, [fetchList]);

  const filtered = items;

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1100 }}>
      <div style={{ marginBottom: 20, display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
        <h1 style={{
          fontFamily: 'var(--sb-font-display)', fontSize: 30, fontWeight: 600,
          margin: 0, letterSpacing: '-0.025em',
        }}>
          Weekly reports
        </h1>
        <span className="sb-label" style={{ color: 'var(--sb-fg-5)' }}>
          {filtered.length} {filtered.length === 1 ? 'report' : 'reports'}
        </span>
        <div style={{ flex: 1 }} />
        <SBButton variant="primary" size="sm" icon="bolt" onClick={() => setShowGen(true)}>
          Generate now
        </SBButton>
      </div>

      {/* Filter bar */}
      <div style={{
        display: 'flex', gap: 10, alignItems: 'center', marginBottom: 20,
        padding: '12px 14px', background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
        flexWrap: 'wrap',
      }}>
        <span className="sb-label" style={{ color: 'var(--sb-fg-5)' }}>Kind</span>
        <div style={{ display: 'flex', gap: 6 }}>
          {KINDS.map((k) => (
            <button
              key={k || 'all'}
              onClick={() => setKind(k)}
              style={{
                padding: '4px 10px', fontSize: 11, fontFamily: 'var(--sb-font-mono)',
                letterSpacing: '0.06em', textTransform: 'uppercase',
                background: kind === k ? 'var(--sb-accent-bg)' : 'transparent',
                color: kind === k ? 'var(--sb-accent)' : 'var(--sb-fg-3)',
                border: `1px solid ${kind === k ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
                cursor: 'pointer',
              }}
            >
              {k || 'all'}
            </button>
          ))}
        </div>
        <div style={{ width: 1, height: 20, background: 'var(--sb-line-2)', margin: '0 4px' }} />
        <span className="sb-label" style={{ color: 'var(--sb-fg-5)' }}>Start after</span>
        <DateInput value={startAfter} onChange={setStartAfter} />
        <span className="sb-label" style={{ color: 'var(--sb-fg-5)' }}>End before</span>
        <DateInput value={endBefore} onChange={setEndBefore} />
        {(kind || startAfter || endBefore) && (
          <SBButton
            variant="ghost" size="xs"
            onClick={() => { setKind(''); setStartAfter(''); setEndBefore(''); }}
          >
            clear
          </SBButton>
        )}
      </div>

      {/* Live analytics \u2014 answers "which sources convert?" + "which
          sequences work?" + "what's my ICP missing?" without needing a
          generated weekly report. */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
        gap: 14, marginBottom: 22,
      }}>
        <SourceRoiCard />
        <SequencePerfCard />
        <IcpRetrospectiveCard />
      </div>

      {loading && (
        <div style={{ color: 'var(--sb-fg-5)', fontSize: 12, fontFamily: 'var(--sb-font-mono)' }}>
          {'loading\u2026'}
        </div>
      )}

      {/* Rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {filtered.map((r) => (
          <SBCard
            key={r.id}
            hover
            onClick={() => navigate(`/admin/reports/${r.id}`)}
            style={{ padding: '16px 20px', display: 'grid',
              gridTemplateColumns: '200px 80px 1fr 120px', gap: 16, alignItems: 'center' }}
          >
            <div>
              <div style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 12.5, color: 'var(--sb-fg)' }}>
                {formatPeriodRange(r)}
              </div>
              <div style={{ fontSize: 10.5, color: 'var(--sb-fg-5)', marginTop: 3,
                fontFamily: 'var(--sb-font-mono)' }}>
                id {String(r.id).slice(0, 8)}
              </div>
            </div>
            <SBChip tone={r.kind === 'weekly' ? 'accent' : 'neutral'}>{r.kind}</SBChip>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: 'flex', gap: 14, marginBottom: 4,
                fontFamily: 'var(--sb-font-mono)', fontSize: 11.5, color: 'var(--sb-fg-3)' }}>
                <span>leads <span style={{ color: 'var(--sb-fg)' }}>{fmtInt(pickStat(r.stats, 'leads.new_leads_count'))}</span></span>
                <span>hot <span style={{ color: 'var(--sb-hot)' }}>{fmtInt(pickStat(r.stats, 'leads.hot_count'))}</span></span>
                <span>reply <span style={{ color: 'var(--sb-accent)' }}>{fmtPercent(pickStat(r.stats, 'automations.reply_rate'))}</span></span>
              </div>
              <div style={{ fontSize: 12.5, color: 'var(--sb-fg-3)', lineHeight: 1.5,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {narrativeExcerpt(r)}
              </div>
            </div>
            <div style={{ textAlign: 'right', fontSize: 10.5, color: 'var(--sb-fg-5)',
              fontFamily: 'var(--sb-font-mono)' }}>
              {r.has_embedding === false ? 'no embed' : 'indexed'}
            </div>
          </SBCard>
        ))}
      </div>

      {filtered.length === 0 && !loading && (
        <SBCard style={{ padding: 28, textAlign: 'center' }}>
          <div className="sb-label" style={{ color: 'var(--sb-fg-5)', marginBottom: 8 }}>No reports</div>
          <div style={{ color: 'var(--sb-fg-4)', fontSize: 13 }}>
            Try clearing filters, or click "Generate now" to kick off a fresh run.
          </div>
        </SBCard>
      )}

      {showGen && <GenerateModal onClose={() => setShowGen(false)} onDone={fetchList} />}
    </div>
  );
}

function DateInput({ value, onChange }) {
  return (
    <input
      type="date"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        padding: '5px 8px', background: 'var(--sb-panel)', border: '1px solid var(--sb-line-2)',
        color: 'var(--sb-fg-2)', fontFamily: 'var(--sb-font-mono)', fontSize: 11.5,
        colorScheme: 'dark',
      }}
    />
  );
}

function GenerateModal({ onClose, onDone }) {
  const navigate = useNavigate();
  const week = currentWeekRange();
  const toISO = (unix) => new Date(unix * 1000).toISOString().slice(0, 10);

  const [kind, setKind] = useState('weekly');
  const [periodStart, setPeriodStart] = useState(toISO(week.start));
  const [periodEnd, setPeriodEnd] = useState(toISO(week.end));
  const [status, setStatus] = useState('idle'); // idle | submitting | error
  const [msg, setMsg] = useState('');

  async function submit() {
    const sa = dateToUnix(periodStart);
    const eb = dateToUnix(periodEnd);
    if (!sa || !eb || sa >= eb) {
      setStatus('error');
      setMsg('Pick a valid period (start must be before end).');
      return;
    }
    setStatus('submitting');
    setMsg('');
    try {
      const job = await api.post('/api/reports/generate', {
        kind, period_start_unix: sa, period_end_unix: eb,
      });
      // If the backend ran inline and already has a report, jump straight in.
      if (job?.status === 'completed' && job?.report_id) {
        navigate(`/admin/reports/${job.report_id}`);
        return;
      }
      // Otherwise it's queued \u2014 close the modal, refresh the list, let the
      // user keep working. The list will show it once it lands.
      onDone?.();
      onClose?.();
    } catch (e) {
      setStatus('error');
      if (e.code === 'rate_limited' || e.status === 429) {
        setMsg('Too many generation requests \u2014 try again in a minute.');
      } else if (isAuthError(e)) {
        navigate('/admin/login', { replace: true });
      } else {
        setMsg(e.message || 'Generation failed.');
      }
    }
  }

  const busy = status === 'submitting';

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="sb-brackets"
        style={{
          width: 440, background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-2)',
          padding: '26px 28px',
        }}
      >
        <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 8 }}>
          Generate report
        </div>
        <h2 style={{ margin: '0 0 18px', fontFamily: 'var(--sb-font-display)', fontSize: 22,
          fontWeight: 600, letterSpacing: '-0.02em' }}>
          Pick kind &amp; period
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <div className="sb-label" style={{ marginBottom: 6 }}>Kind</div>
            <div style={{ display: 'flex', gap: 6 }}>
              {['weekly', 'daily', 'monthly', 'custom'].map((k) => (
                <button
                  key={k}
                  onClick={() => setKind(k)}
                  disabled={busy}
                  style={{
                    padding: '6px 12px', fontSize: 11.5, fontFamily: 'var(--sb-font-mono)',
                    letterSpacing: '0.06em', textTransform: 'uppercase',
                    background: kind === k ? 'var(--sb-accent)' : 'transparent',
                    color: kind === k ? '#000' : 'var(--sb-fg-3)',
                    border: `1px solid ${kind === k ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
                    cursor: busy ? 'not-allowed' : 'pointer', opacity: busy ? 0.6 : 1,
                  }}
                >
                  {k}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <div className="sb-label" style={{ marginBottom: 6 }}>Start</div>
              <DateInput value={periodStart} onChange={setPeriodStart} />
            </div>
            <div>
              <div className="sb-label" style={{ marginBottom: 6 }}>End (exclusive)</div>
              <DateInput value={periodEnd} onChange={setPeriodEnd} />
            </div>
          </div>

          {msg && (
            <div style={{
              fontFamily: 'var(--sb-font-mono)', fontSize: 11.5,
              color: status === 'error' ? 'var(--sb-hot)' : 'var(--sb-fg-3)',
              padding: '10px 12px', background: 'var(--sb-panel)',
              border: '1px solid var(--sb-line-2)',
            }}>
              {msg}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 22 }}>
          <SBButton variant="ghost" onClick={onClose} disabled={busy}>Cancel</SBButton>
          <SBButton variant="primary" icon="bolt" onClick={submit} disabled={busy}>
            {busy ? 'Submitting\u2026' : 'Generate'}
          </SBButton>
        </div>
      </div>
    </div>
  );
}


// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// Live analytics cards \u2014 answer "which sources convert?" and "which
// sequences work?" with cumulative cohort data. Live = no manual report
// generation needed; they update as new replies land.
// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

function SourceRoiCard() {
  const [items, setItems] = useState(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get('/api/reports/source-roi', { fresh: true });
        if (!cancelled) setItems(r?.items || []);
      } catch {
        if (!cancelled) setItems([]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <SBCard style={{ padding: 18 }} bracket>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
        <span className="sb-label" style={{ color: 'var(--sb-accent)' }}>Source ROI</span>
        <span style={{ fontSize: 11, color: 'var(--sb-fg-5)' }}>which scrapers convert?</span>
      </div>
      {items === null && <div style={{ fontSize: 12, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>\u25b8 loading\u2026</div>}
      {items && items.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--sb-fg-5)' }}>
          No leads yet \u2014 convert some captures to see source breakdown.
        </div>
      )}
      {items && items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.slice(0, 8).map((row) => (
            <SourceRow key={row.source} row={row} max={items[0]?.lead_count || 1} />
          ))}
        </div>
      )}
    </SBCard>
  );
}

function SourceRow({ row, max }) {
  const pct = Math.max(2, Math.round((row.lead_count / max) * 100));
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr 96px', gap: 10, alignItems: 'center' }}>
      <span style={{ fontSize: 12, color: 'var(--sb-fg-3)', fontFamily: 'var(--sb-font-mono)',
                     overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {row.source}
      </span>
      <div style={{ position: 'relative', height: 6, background: 'var(--sb-line-2)' }}>
        <div style={{ position: 'absolute', inset: 0, width: `${pct}%`,
                       background: row.replied_count > 0 ? 'var(--sb-accent)' : 'var(--sb-fg-5)' }} />
      </div>
      <div style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-3)', textAlign: 'right' }}>
        <span style={{ color: 'var(--sb-accent)' }}>{row.replied_count}</span>
        {' / '}
        <span>{row.lead_count}</span>
        {' '}
        <span style={{ color: 'var(--sb-fg-5)' }}>
          {(row.reply_rate * 100).toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

function IcpRetrospectiveCard() {
  const [data, setData] = useState(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get('/api/leads/icp-retrospective', { fresh: true });
        if (!cancelled) setData(r);
      } catch {
        if (!cancelled) setData({ ok: false });
      }
    })();
  }, []);

  return (
    <SBCard style={{ padding: 18 }} bracket>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
        <span className="sb-label" style={{ color: 'var(--sb-accent)' }}>ICP retrospective</span>
        <span style={{ fontSize: 11, color: 'var(--sb-fg-5)' }}>what your hot leads have in common</span>
      </div>
      {data === null && <div style={{ fontSize: 12, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>▸ loading…</div>}
      {data && !data.ok && (
        <div style={{ fontSize: 12, color: 'var(--sb-fg-5)', lineHeight: 1.55 }}>
          {data.message || 'Not enough hot/replied leads to cluster yet.'}
        </div>
      )}
      {data && data.ok && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8,
            fontFamily: 'var(--sb-font-mono)', fontSize: 11,
          }}>
            <Stat label="leads"   value={data.lead_count} />
            <Stat label="replied" value={data.replied_count} tone="lime" />
            <Stat label="avg"     value={data.avg_score} />
          </div>
          {(data.suggestions || []).length > 0 && (
            <div style={{
              padding: '10px 12px', background: 'var(--sb-accent-bg)',
              border: '1px solid var(--sb-accent)',
            }}>
              {(data.suggestions || []).map((s, i) => (
                <div key={i} style={{
                  fontSize: 12, color: 'var(--sb-fg-2)', lineHeight: 1.5,
                  marginBottom: i < data.suggestions.length - 1 ? 6 : 0,
                }}>
                  ▸ {s}
                </div>
              ))}
            </div>
          )}
          <Distribution label="Top sources"  rows={data.top_sources} />
          <Distribution label="Top triggers" rows={data.top_triggers} />
          {data.top_titles?.length > 0 && (
            <Distribution label="Top titles" rows={data.top_titles} />
          )}
        </div>
      )}
    </SBCard>
  );
}

function Stat({ label, value, tone }) {
  const COLOR = { lime: 'var(--sb-lime)', hot: 'var(--sb-hot)' };
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <span style={{ fontSize: 16, fontWeight: 600, color: COLOR[tone] || 'var(--sb-fg)', lineHeight: 1 }}>
        {value}
      </span>
      <span style={{
        fontSize: 9.5, color: 'var(--sb-fg-5)', textTransform: 'uppercase',
        letterSpacing: '0.08em', marginTop: 3,
      }}>{label}</span>
    </div>
  );
}

function Distribution({ label, rows }) {
  if (!rows || rows.length === 0) return null;
  return (
    <div>
      <div style={{
        fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
        textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4,
      }}>{label}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {rows.slice(0, 5).map((r) => (
          <div key={r.value} style={{
            display: 'grid', gridTemplateColumns: '1fr auto', gap: 8,
            fontSize: 11.5, color: 'var(--sb-fg-3)', fontFamily: 'var(--sb-font-mono)',
          }}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.value}</span>
            <span style={{ color: 'var(--sb-fg-5)' }}>{r.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}


function SequencePerfCard() {
  const [items, setItems] = useState(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get('/api/reports/sequence-performance', { fresh: true });
        if (!cancelled) setItems(r?.items || []);
      } catch {
        if (!cancelled) setItems([]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <SBCard style={{ padding: 18 }} bracket>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
        <span className="sb-label" style={{ color: 'var(--sb-accent)' }}>Sequence performance</span>
        <span style={{ fontSize: 11, color: 'var(--sb-fg-5)' }}>which templates get replies?</span>
      </div>
      {items === null && <div style={{ fontSize: 12, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>\u25b8 loading\u2026</div>}
      {items && items.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--sb-fg-5)' }}>
          No sequences run yet.
        </div>
      )}
      {items && items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {items.slice(0, 6).map((row) => (
            <div key={row.template_id} style={{
              display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'baseline',
            }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12.5, color: 'var(--sb-fg)', fontWeight: 600 }}>
                  {row.template_name}
                </div>
                <div style={{ fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
                  {row.sends_total} sent \u00b7 {row.replied_total} replied
                  {row.skipped_replied > 0 && ` \u00b7 ${row.skipped_replied} skipped (already replied)`}
                </div>
              </div>
              <div style={{
                fontFamily: 'var(--sb-font-mono)', fontSize: 18, fontWeight: 600,
                color: row.replied_total > 0 ? 'var(--sb-accent)' : 'var(--sb-fg-5)',
              }}>
                {(row.reply_rate * 100).toFixed(1)}<span style={{ fontSize: 11, color: 'var(--sb-fg-5)' }}>%</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </SBCard>
  );
}

