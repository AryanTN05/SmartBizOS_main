import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../../../lib/api.js';
import { useLaraUI } from '../../../lib/LaraUIContext.jsx';
import { SBButton } from '../../../components/primitives';
import ReportView from '../components/ReportView.jsx';
import { isAuthError, pickStat, fmtDelta } from '../lib/format.js';

export default function ReportCompare() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { openDrawer } = useLaraUI();
  const a = params.get('a');
  const b = params.get('b');

  const [pair, setPair] = useState({ a: null, b: null });
  const [loading, setLoading] = useState(true);
  const [fatal, setFatal] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFatal(null);

    async function go() {
      if (!a || !b) {
        setFatal({ code: 'validation', message: 'Missing compare ids (?a=&b=).' });
        setLoading(false);
        return;
      }
      try {
        const r = await api.get(
          `/api/reports/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`
        );
        if (cancelled) return;
        setPair({ a: r?.a, b: r?.b });
        setLoading(false);
      } catch (e) {
        if (cancelled) return;
        if (isAuthError(e)) {
          navigate('/admin/login', { replace: true });
          return;
        }
        setFatal({ code: e.code || 'error', message: e.message || 'Could not load comparison.' });
        setLoading(false);
      }
    }

    go();
    return () => { cancelled = true; };
  }, [a, b, navigate]);

  const deltas = useMemo(() => {
    if (!pair.a || !pair.b) return {};
    const paths = [
      ['leads.new_leads_count', 'New leads'],
      ['leads.hot_count', 'Hot'],
      ['automations.reply_rate', 'Reply rate'],
      ['automations.runs_total', 'Runs'],
    ];
    const out = {};
    for (const [p, label] of paths) {
      const av = pickStat(pair.a.stats, p, null);
      const bv = pickStat(pair.b.stats, p, null);
      if (typeof av === 'number' && typeof bv === 'number') {
        out[label] = { a: av, b: bv, delta: fmtDelta(av, bv) };
      }
    }
    return out;
  }, [pair]);

  if (fatal) {
    return (
      <div style={{ padding: '48px 32px', maxWidth: 520 }}>
        <div className="sb-label" style={{ color: 'var(--sb-hot)', marginBottom: 8 }}>
          {fatal.code}
        </div>
        <h1 style={{ margin: 0, fontFamily: 'var(--sb-font-display)', fontSize: 26,
          fontWeight: 500, letterSpacing: '-0.02em' }}>
          {fatal.message}
        </h1>
        <div style={{ marginTop: 18 }}>
          <SBButton variant="secondary" onClick={() => navigate('/admin/reports')}>
            Back to reports
          </SBButton>
        </div>
      </div>
    );
  }

  if (loading || !pair.a || !pair.b) {
    return (
      <div style={{ padding: '48px 32px', color: 'var(--sb-fg-5)',
        fontFamily: 'var(--sb-font-mono)', fontSize: 12 }}>
        {'loading comparison\u2026'}
      </div>
    );
  }

  return (
    <div style={{ padding: '28px 32px' }}>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 14,
        flexWrap: 'wrap' }}>
        <SBButton variant="ghost" size="xs" icon="arrow" onClick={() => navigate('/admin/reports')}>
          All reports
        </SBButton>
        <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 600,
          margin: 0, letterSpacing: '-0.025em' }}>
          Compare
        </h1>
        <div style={{ flex: 1 }} />
        <SBButton
          variant="primary" size="sm" icon="lara"
          onClick={() => openDrawer({
            prompt: 'Synthesize a comparison narrative between these two reports. Call out the biggest movers and likely causes.',
            reports: [pair.a, pair.b],
          })}
        >
          Ask Lara to synthesize
        </SBButton>
      </div>

      {/* Inline deltas strip */}
      {Object.keys(deltas).length > 0 && (
        <div style={{
          display: 'grid', gridTemplateColumns: `repeat(${Object.keys(deltas).length}, 1fr)`,
          gap: 12, marginBottom: 22,
          padding: '14px 16px', background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
        }}>
          {Object.entries(deltas).map(([label, { a: av, b: bv, delta }]) => {
            const up = delta && delta.startsWith('+');
            return (
              <div key={label}>
                <div className="sb-label">{label}</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6,
                  fontFamily: 'var(--sb-font-mono)' }}>
                  <span style={{ fontSize: 16, color: 'var(--sb-fg)' }}>{fmtNum(av)}</span>
                  <span style={{ fontSize: 11, color: 'var(--sb-fg-5)' }}>vs</span>
                  <span style={{ fontSize: 13, color: 'var(--sb-fg-3)' }}>{fmtNum(bv)}</span>
                  {delta && (
                    <span style={{ fontSize: 11, fontWeight: 700,
                      color: up ? 'var(--sb-accent)' : 'var(--sb-warm)' }}>
                      {delta}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <div>
          <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 10 }}>A</div>
          <ReportView report={pair.a} compact />
        </div>
        <div>
          <div className="sb-label" style={{ color: 'var(--sb-violet)', marginBottom: 10 }}>B</div>
          <ReportView report={pair.b} compact />
        </div>
      </div>
    </div>
  );
}

function fmtNum(v) {
  if (typeof v !== 'number') return '\u2014';
  if (v < 1 && v > 0) return `${(v * 100).toFixed(1)}%`;
  return String(v);
}
