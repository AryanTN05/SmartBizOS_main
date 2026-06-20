import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBCard, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../../leads/lib/toast.jsx';

// Empty-state diagnostics for /admin/inbox.
//
// When the lead-count query returns 0, the page mounts this instead of a
// generic "no leads yet" message. We GET /api/inbox/diagnostics, classify
// the workspace's state, and render one of 4 cards — each with a single
// concrete next action.
//
// Cards:
//   A — run_scraper      no scraper has ever fired
//   B — check_sources    scrapers ran but found 0 raw results in 7d
//   C — lower_threshold  raw results exist but none clear the HOT bar
//   D — loosen_icp       raw results exist but ICP filter killed them
//
// Failure-mode contract: if the diagnostics endpoint 500s, we render a
// minimal fallback so the page never breaks. Telemetry-friendly: each card
// fires a single descriptive event on render so PMs can A/B copy later.

const formatRelTime = (unix) => {
  if (!unix) return null;
  const ageMs = Date.now() - unix * 1000;
  const m = Math.floor(ageMs / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
};

export default function EmptyStateDiagnostic() {
  const navigate = useNavigate();
  const [diag, setDiag] = useState(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get('/api/inbox/diagnostics', { fresh: true });
        if (!cancelled) setDiag(r);
      } catch (err) {
        if (!cancelled) setError(true);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const lowerThreshold = async () => {
    setBusy(true);
    try {
      await api.patch('/api/workspace/settings', { slack_alert_min_score: 50 });
      toast.success('Threshold set to 50 · refreshing…');
      // Quick reload so the inbox re-queries with new threshold + diagnostics
      // re-classifies. setTimeout to let the toast read.
      setTimeout(() => window.location.reload(), 600);
    } catch (err) {
      toast.error(err?.message || 'Could not update threshold');
    } finally {
      setBusy(false);
    }
  };

  // ---- fallback states ----
  if (error) {
    return <Bare onScrapers={() => navigate('/admin/scrapers')} />;
  }
  if (diag === null) {
    return <Skeleton />;
  }

  // ---- card chooser ----
  switch (diag.recommended_action) {
    case 'run_scraper':
      return (
        <DiagCard
          accent="accent"
          eyebrow="Step 1 of triage"
          title="No scrapers have run yet."
          body="SmartBiz pulls leads from eight configured sources (YC, Apollo, HN, Product Hunt, GitHub Trending, TechCrunch, Hunter, LinkedIn fixtures). Kick one off — captures will land here scored against your ICP."
          stat={<Stat label="last run" value="—" />}
          cta={
            <SBButton variant="primary" size="sm" icon="bolt"
              onClick={() => navigate('/admin/scrapers')}>
              Run a scraper now
            </SBButton>
          }
        />
      );

    case 'check_sources':
      return (
        <DiagCard
          accent="warm"
          eyebrow="Quiet sources"
          title="Your scrapers ran but found nothing."
          body={
            <>
              Last run was <strong>{formatRelTime(diag.last_scraper_run_at_unix) || 'a while ago'}</strong>{' '}
              and surfaced <strong>0</strong> raw captures in the last 7 days.
              Either the sources are quiet this week, or some need a re-fetch.
              Open the scrapers page to inspect each source.
            </>
          }
          stat={<Stat label="raw 7d" value={diag.raw_results_7d} />}
          cta={
            <SBButton variant="primary" size="sm" icon="eye"
              onClick={() => navigate('/admin/scrapers')}>
              Inspect scrapers
            </SBButton>
          }
        />
      );

    case 'all_triaged':
      return (
        <DiagCard
          accent="accent"
          eyebrow="Inbox zero"
          title="Nothing pending — you're caught up."
          body={
            <>
              You've already triaged every recent capture. Last 7 days
              surfaced <strong>{diag.raw_results_7d}</strong> raw rows; all
              are either converted to leads or dismissed. Run a scraper
              again to refresh the queue, or check the converted leads in{' '}
              <strong>/admin/leads</strong>.
            </>
          }
          stat={<Stat label="triaged 7d" value={diag.raw_results_7d} />}
          cta={
            <>
              <SBButton variant="primary" size="sm" icon="bolt"
                onClick={() => navigate('/admin/scrapers')}>
                Run a scraper
              </SBButton>
              <SBButton variant="ghost" size="sm" iconRight="arrow"
                onClick={() => navigate('/admin/leads')}>
                View converted leads
              </SBButton>
            </>
          }
        />
      );

    case 'lower_threshold':
      return (
        <DiagCard
          accent="hot"
          eyebrow="Threshold gate"
          title={`We found ${diag.pending_total} leads — none scored above your bar of ${diag.alert_threshold}.`}
          body={
            <>
              Lots of medium-fit captures, no clear HOT yet. You can drop
              the HOT threshold to <strong>50</strong> and let the
              tiered Inbox surface them as WARM/NURTURE — or revisit the
              ICP wizard so the scorer becomes pickier in the right way.
            </>
          }
          stat={<ScoreHistogram h={diag.score_histogram} />}
          cta={
            <>
              <SBButton variant="primary" size="sm" icon="bolt"
                disabled={busy} onClick={lowerThreshold}>
                {busy ? 'Updating…' : 'Set threshold to 50'}
              </SBButton>
              <SBButton variant="ghost" size="sm"
                onClick={() => navigate('/admin/settings')}>
                Edit ICP instead
              </SBButton>
            </>
          }
        />
      );

    case 'loosen_icp':
      return (
        <DiagCard
          accent="cool"
          eyebrow="ICP too narrow"
          title="Your ICP rejected almost everything we found."
          body={
            <>
              Of <strong>{diag.pending_total}</strong> recent captures,{' '}
              <strong>{diag.score_histogram['0_30']}</strong> scored below 30 —
              that's the model telling you the ICP is too tight or describes
              a niche that this week's sources don't surface. Re-run the ICP
              wizard with a broader archetype, or edit the description directly.
            </>
          }
          stat={<ScoreHistogram h={diag.score_histogram} />}
          cta={
            <SBButton variant="primary" size="sm" icon="spark"
              onClick={() => navigate('/admin/settings')}>
              Loosen the ICP
            </SBButton>
          }
        />
      );

    case 'none':
    default:
      // The page shouldn't really mount this in this state (means there
      // ARE pending leads but the current filter excluded them). Render a
      // soft hint pointing at filters.
      return (
        <DiagCard
          accent="accent"
          eyebrow="Filtered view"
          title="No captures match the current filter."
          body="There are pending captures but they're not showing under the active tier/source filter. Reset filters to see the full queue."
          stat={null}
          cta={
            <SBButton variant="ghost" size="sm" icon="close"
              onClick={() => window.location.reload()}>
              Reset filters
            </SBButton>
          }
        />
      );
  }
}

// ─── presentation ──────────────────────────────────────────────────────────

function DiagCard({ accent, eyebrow, title, body, stat, cta }) {
  const accentColor = {
    accent: 'var(--sb-accent)',
    hot:    'var(--sb-hot)',
    warm:   'var(--sb-warm)',
    cool:   'var(--sb-cool)',
  }[accent] || 'var(--sb-accent)';

  return (
    <div style={{ padding: '40px 32px', maxWidth: 720 }}>
      <div style={{
        background: 'var(--sb-bg-2)',
        border: '1px solid var(--sb-line-2)',
        borderLeft: `2px solid ${accentColor}`,
        padding: '24px 28px',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 10.5, color: accentColor,
          fontFamily: 'var(--sb-font-mono)',
          textTransform: 'uppercase', letterSpacing: '0.14em',
          marginBottom: 14,
        }}>
          <SBIcon name="dot" size={6} />
          <span>{eyebrow}</span>
        </div>
        <h2 style={{
          fontFamily: 'var(--sb-font-display)', fontSize: 22, fontWeight: 600,
          letterSpacing: '-0.015em', margin: 0, lineHeight: 1.25,
          color: 'var(--sb-fg)',
        }}>{title}</h2>
        <p style={{
          marginTop: 12, color: 'var(--sb-fg-3)',
          fontSize: 13.5, lineHeight: 1.65, maxWidth: 560,
        }}>{body}</p>
        {stat && <div style={{ marginTop: 18 }}>{stat}</div>}
        <div style={{
          marginTop: 22, display: 'flex', gap: 8, flexWrap: 'wrap',
        }}>
          {cta}
        </div>
      </div>
      <div style={{
        marginTop: 12, fontSize: 11, color: 'var(--sb-fg-5)',
        fontFamily: 'var(--sb-font-mono)', letterSpacing: '0.04em',
      }}>
        ▸ tip: the Inbox refreshes itself after each fix
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={{
      display: 'inline-flex', flexDirection: 'column', gap: 2,
      padding: '10px 14px',
      background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
    }}>
      <div style={{
        fontSize: 9.5, color: 'var(--sb-fg-5)',
        fontFamily: 'var(--sb-font-mono)',
        textTransform: 'uppercase', letterSpacing: '0.12em',
      }}>{label}</div>
      <div style={{
        fontSize: 18, fontFamily: 'var(--sb-font-mono)',
        color: 'var(--sb-fg)', fontWeight: 500,
      }}>{value}</div>
    </div>
  );
}

// Inline 4-bucket histogram for the threshold/icp cards. Drawn with CSS,
// no chart lib — keeps the bundle small + the aesthetic consistent.
function ScoreHistogram({ h }) {
  const total = (h['0_30'] || 0) + (h['30_50'] || 0) + (h['50_70'] || 0) + (h['70_100'] || 0);
  const buckets = [
    { key: '0_30',   label: '0–30',   tone: 'var(--sb-fg-5)',  v: h['0_30']   || 0 },
    { key: '30_50',  label: '30–50',  tone: 'var(--sb-cool)',  v: h['30_50']  || 0 },
    { key: '50_70',  label: '50–70',  tone: 'var(--sb-warm)',  v: h['50_70']  || 0 },
    { key: '70_100', label: '70–100', tone: 'var(--sb-hot)',   v: h['70_100'] || 0 },
  ];
  const maxV = Math.max(1, ...buckets.map((b) => b.v));
  return (
    <div style={{
      display: 'inline-flex', gap: 12, alignItems: 'flex-end',
      padding: '12px 16px',
      background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
    }}>
      {buckets.map((b) => {
        const heightPct = Math.round((b.v / maxV) * 100);
        return (
          <div key={b.key} style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
            minWidth: 40,
          }}>
            <div style={{
              fontFamily: 'var(--sb-font-mono)', fontSize: 12,
              color: b.tone, fontWeight: 500,
            }}>{b.v}</div>
            <div style={{
              width: 18, height: 32, position: 'relative',
              border: `1px solid var(--sb-line-2)`,
              background: 'var(--sb-panel)',
            }}>
              <div style={{
                position: 'absolute', bottom: 0, left: 0, right: 0,
                height: `${Math.max(2, heightPct)}%`,
                background: b.tone, opacity: b.v === 0 ? 0.15 : 0.85,
              }} />
            </div>
            <div style={{
              fontSize: 9.5, color: 'var(--sb-fg-5)',
              fontFamily: 'var(--sb-font-mono)', letterSpacing: '0.04em',
            }}>{b.label}</div>
          </div>
        );
      })}
      <div style={{
        marginLeft: 8, paddingLeft: 12, borderLeft: '1px solid var(--sb-line-2)',
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
      }}>
        <div style={{
          fontSize: 9.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
          textTransform: 'uppercase', letterSpacing: '0.1em',
        }}>total</div>
        <div style={{
          fontFamily: 'var(--sb-font-mono)', fontSize: 16, color: 'var(--sb-fg)',
        }}>{total}</div>
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div style={{ padding: '40px 32px', maxWidth: 720 }}>
      <div style={{
        background: 'var(--sb-bg-2)', border: '1px solid var(--sb-line-2)',
        padding: '24px 28px', opacity: 0.5,
      }}>
        <div style={{ width: 90, height: 10, background: 'var(--sb-card)', marginBottom: 14 }} />
        <div style={{ width: '70%', height: 22, background: 'var(--sb-card)', marginBottom: 12 }} />
        <div style={{ width: '90%', height: 12, background: 'var(--sb-card)', marginBottom: 6 }} />
        <div style={{ width: '60%', height: 12, background: 'var(--sb-card)', marginBottom: 18 }} />
        <div style={{ width: 140, height: 32, background: 'var(--sb-card)' }} />
      </div>
    </div>
  );
}

// Last-resort fallback if the diagnostics endpoint 500s. Mirrors the
// pre-diagnostic empty state so the page never visibly breaks.
function Bare({ onScrapers }) {
  return (
    <div style={{ padding: '40px 32px', maxWidth: 620 }}>
      <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 6 }}>Triage</div>
      <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 600, margin: 0, letterSpacing: '-0.02em' }}>
        Nothing to triage yet.
      </h1>
      <p style={{ marginTop: 10, color: 'var(--sb-fg-4)', fontSize: 13.5, lineHeight: 1.6 }}>
        Captures land here after a scraper run + enrichment pass.
      </p>
      <div style={{ marginTop: 18 }}>
        <SBButton variant="primary" size="sm" icon="bolt" onClick={onScrapers}>
          Open scrapers
        </SBButton>
      </div>
    </div>
  );
}
