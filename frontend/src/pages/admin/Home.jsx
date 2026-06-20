import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBCard, SBIcon, SBStat } from '../../components/primitives';
import { useLaraUI } from '../../lib/LaraUIContext.jsx';
import { useSession } from '../../lib/SessionContext.jsx';
import api from '../../lib/api.js';
import { toast, ToastHost } from '../../modules/leads/lib/toast.jsx';
import FirstSendWizard from '../../modules/onboarding/FirstSendWizard.jsx';

// One-line setup-checklist row used by the empty-workspace home view.
function SetupStep({ num, title, blurb, cta, onClick }) {
  return (
    <SBCard
      style={{
        padding: '16px 20px',
        display: 'flex', alignItems: 'center', gap: 16,
      }}
    >
      <div style={{
        width: 32, height: 32, flexShrink: 0,
        background: 'var(--sb-accent-bg)', color: 'var(--sb-accent)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'var(--sb-font-mono)', fontSize: 13, fontWeight: 600,
      }}>{num}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>{title}</div>
        <div style={{ fontSize: 12, color: 'var(--sb-fg-4)', lineHeight: 1.5 }}>{blurb}</div>
      </div>
      <SBButton variant="ghost" size="sm" iconRight="arrow" onClick={onClick}>{cta}</SBButton>
    </SBCard>
  );
}

// Greeting that flexes with local time so demo screenshots feel alive.
function greeting() {
  const h = new Date().getHours();
  if (h < 5) return 'Late night';
  if (h < 12) return 'Morning';
  if (h < 17) return 'Afternoon';
  if (h < 21) return 'Evening';
  return 'Late night';
}

export default function Home() {
  const navigate = useNavigate();
  const { openDrawer } = useLaraUI();
  const { session } = useSession();
  const name = session?.kind === 'admin'
    ? (session.admin?.name?.split(' ')[0] || 'there')
    : 'there';

  const [leads, setLeads] = useState(null);
  const [runs, setRuns] = useState(null);
  const [latestReport, setLatestReport] = useState(null);
  const [seqStats, setSeqStats] = useState(null); // live reply-rate
  const [showFirstSend, setShowFirstSend] = useState(false);

  // Fan out four reads in parallel — Home is the page that establishes the
  // "live not seeded" feeling before the user navigates anywhere else. Reply
  // rate is now live (off lead.sequence_state) so a Day-2 user sees feedback
  // without manually generating a weekly report.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const settle = (p) => p.then((v) => v).catch(() => null);
      const [ls, rs, lr, ss] = await Promise.all([
        settle(api.get('/api/leads?limit=100')),
        settle(api.get('/api/automations/runs?limit=100')),
        settle(api.get('/api/reports/latest?kind=weekly')),
        settle(api.get('/api/leads/sequence-stats')),
      ]);
      if (cancelled) return;
      setLeads(ls?.items || (Array.isArray(ls) ? ls : []));
      setRuns(rs?.items || (Array.isArray(rs) ? rs : []));
      setLatestReport(lr || null);
      setSeqStats(ss || null);
    })();
    return () => { cancelled = true; };
  }, []);

  const scoreOf = (l) => (typeof l?.score === 'object' ? (l.score?.value ?? 0) : (l?.score ?? 0));

  const stats = useMemo(() => {
    const activeLeads = leads ? leads.filter((l) => l.status !== 'lost').length : null;
    const hotCount = leads ? leads.filter((l) => scoreOf(l) >= 75).length : null;
    const runs24h = runs
      ? runs.filter((r) => r.started_at_unix > Math.floor(Date.now() / 1000) - 86400).length
      : null;
    const failed24h = runs
      ? runs.filter((r) => r.status === 'failed' && r.started_at_unix > Math.floor(Date.now() / 1000) - 86400).length
      : null;
    // Live reply rate beats the report's stale snapshot when we have it. The
    // report only refreshes on Mondays via cron — Day 2 users would see "—"
    // and bounce. Live data: replied_total / in_sequence_total.
    const liveRate = seqStats?.in_sequence_total ? seqStats.reply_rate : null;
    const replyRate = liveRate != null ? liveRate : latestReport?.stats?.automations?.reply_rate;
    const replySource = liveRate != null ? 'live' : (replyRate != null ? 'weekly' : null);
    const replied7d = seqStats?.replied_7d ?? null;
    return { activeLeads, hotCount, runs24h, failed24h, replyRate, replySource, replied7d };
  }, [leads, runs, latestReport, seqStats]);

  const headline = useMemo(() => {
    const h = stats.hotCount;
    const f = stats.failed24h;
    const reportPart = latestReport
      ? `1 report ${latestReport.id?.startsWith('seed-') ? 'waiting' : 'fresh'}.`
      : '1 report waiting.';
    return `${h ?? '—'} hot. ${f ?? '—'} failed runs. ${reportPart}`;
  }, [stats.hotCount, stats.failed24h, latestReport]);

  const topLead = useMemo(() => {
    if (!leads || !leads.length) return null;
    const sorted = [...leads].sort((a, b) => scoreOf(b) - scoreOf(a));
    return sorted[0];
  }, [leads]);

  // "Empty workspace" detection — when the user has loaded the app but
  // hasn't actually run anything yet, the original UI shows "—. —. —"
  // which feels broken. The setup checklist gives a clear next action.
  const ready = leads !== null && runs !== null;
  const isEmpty = ready
    && (leads?.length || 0) === 0
    && (runs?.length || 0) === 0
    && !latestReport;

  if (isEmpty) {
    return (
      <div style={{ padding: '28px 32px', maxWidth: 760 }}>
        <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 8 }}>
          {greeting()}, {name}
        </div>
        <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 32, fontWeight: 600, margin: 0, letterSpacing: '-0.02em' }}>
          Let's get your workspace going.
        </h1>
        <p style={{ marginTop: 10, color: 'var(--sb-fg-4)', fontSize: 13.5, lineHeight: 1.6, maxWidth: 580 }}>
          Four steps to see SmartBiz scoring + sequencing real leads. Each one
          unlocks a piece of the picture you'll see on this page.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 24 }}>
          <SetupStep
            num={1} title="Set your ICP"
            blurb="One paragraph describing who's a fit — the LLM scorer reads this every enrichment pass."
            cta="Open settings"
            onClick={() => navigate('/admin/settings')}
          />
          <SetupStep
            num={2} title="Run a scraper"
            blurb="Eight live sources are wired (YC, Apollo, HN, Product Hunt, GitHub Trending, TechCrunch, Hunter)."
            cta="Open scrapers"
            onClick={() => navigate('/admin/scrapers')}
          />
          <SetupStep
            num={3} title="Or import a CSV"
            blurb="Already have a list? Paste/upload — auto-mapped headers, dedupes on email."
            cta="Open leads"
            onClick={() => navigate('/admin/leads')}
          />
          <SetupStep
            num={4} title="Generate a report"
            blurb="A weekly cross-module summary so this Home page stops looking empty."
            cta="Open reports"
            onClick={() => navigate('/admin/reports')}
          />
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{ marginBottom: 28 }}>
        <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 8 }}>
          {greeting()}, {name}
        </div>
        <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 36, fontWeight: 600, margin: 0, letterSpacing: '-0.025em' }}>
          {headline.split('.').filter(Boolean).slice(0, 2).join('.') + '.'}
          <span style={{ color: 'var(--sb-fg-5)' }}>{' ' + headline.split('.').filter(Boolean).slice(2).join('.') + '.'}</span>
        </h1>
      </div>

      {/* Quick actions row — top-of-page so users can fire off the
          daily digest or jump to any heavy action without scrolling. */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        <SBButton variant="primary" size="sm" icon="bolt"
          onClick={() => setShowFirstSend(true)}>
          First send · 60s
        </SBButton>
        <SBButton variant="ghost" size="sm" icon="mail"
          onClick={async () => {
            try {
              const r = await api.post('/api/workspace/settings/digest/send-now');
              if (r?.ok) {
                const s = r.stats || {};
                toast.success(`Digest sent to ${(r.sent_to || []).length} admin · ${s.replies || 0} replies, ${s.hot || 0} hot`);
              } else {
                toast.info(r?.message || 'No activity in the last 24h');
              }
            } catch (err) {
              toast.error(err?.message || 'Digest failed');
            }
          }}>
          Send daily digest
        </SBButton>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 28 }}>
        <SBStat label="Active leads"  value={stats.activeLeads ?? '—'}                               mono />
        <SBStat label="Hot"           value={stats.hotCount    ?? '—'} delta=" "  trend="up"         mono />
        <SBStat label="Runs · 24h"    value={stats.runs24h     ?? '—'}
                delta={stats.failed24h ? `${stats.failed24h} failed` : 'all green'}
                trend={stats.failed24h ? 'hot' : 'up'} mono />
        <SBStat
          label={stats.replySource === 'live' ? 'Reply rate · live' : 'Reply rate'}
          value={stats.replyRate != null
            ? `${(stats.replyRate * 100).toFixed(1)}%` : '—'}
          delta={stats.replied7d ? `${stats.replied7d} in 7d` : (stats.replySource === 'weekly' ? 'from weekly' : ' ')}
          trend={stats.replied7d ? 'up' : undefined}
          mono />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 16 }}>
        <SBCard style={{ padding: 24 }} bracket>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <div style={{
              width: 28, height: 28, background: 'var(--sb-accent-bg)', color: 'var(--sb-accent)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <SBIcon name="lara" size={14} stroke={1.4} />
            </div>
            <span className="sb-label">Lara · suggested</span>
          </div>
          <p style={{ fontSize: 17, lineHeight: 1.5, color: 'var(--sb-fg)', margin: '0 0 18px', fontFamily: 'var(--sb-font-display)', fontWeight: 500, letterSpacing: '-0.01em' }}>
            {topLead
              ? <>"{topLead.name} just opened your day-0 email. They're at <span style={{ color: 'var(--sb-accent)' }}>{scoreOf(topLead)}</span>. Want me to queue a follow-up and loop in sales?"</>
              : <>"Looking quiet today — want me to scan the LinkedIn pipe and surface any new ICP matches?"</>}
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <SBButton
              variant="primary" icon="bolt"
              onClick={() => openDrawer({
                prompt: topLead
                  ? `Queue a follow-up for ${topLead.name} and loop in sales.`
                  : 'Scan recent leads and surface anything that looks ICP-fit.',
              })}
            >
              Yes, do it
            </SBButton>
            <SBButton variant="ghost" onClick={() => openDrawer()}>Ask more</SBButton>
          </div>
        </SBCard>

        <SBCard style={{ padding: 24 }}>
          <div className="sb-label" style={{ marginBottom: 14 }}>
            {latestReport ? 'Last week · in one sentence' : 'Reports'}
          </div>
          <p style={{ fontSize: 15, lineHeight: 1.55, color: 'var(--sb-fg-2)', margin: '0 0 12px' }}>
            {latestReport?.headline
              ? latestReport.headline
              : 'No report yet — generate one to see how the week shaped up.'}
          </p>
          <SBButton
            variant="ghost" size="sm" iconRight="arrow"
            onClick={() => navigate(latestReport ? `/admin/reports/${latestReport.id}` : '/admin/reports')}
          >
            {latestReport ? 'Full report' : 'Reports'}
          </SBButton>
        </SBCard>
      </div>
      {showFirstSend && <FirstSendWizard onClose={() => setShowFirstSend(false)} />}
      <ToastHost />
    </div>
  );
}
