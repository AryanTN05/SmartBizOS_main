import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api from '../../../lib/api.js';
import { useLaraUI } from '../../../lib/LaraUIContext.jsx';
import { SBButton } from '../../../components/primitives';
import { toast } from '../../leads/lib/toast.jsx';
import ReportView from '../components/ReportView.jsx';
import { isAuthError } from '../lib/format.js';

export default function ReportDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { openDrawer } = useLaraUI();

  const [report, setReport] = useState(null);
  const [trend, setTrend] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fatal, setFatal] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFatal(null);

    async function go() {
      // Primary fetch.
      let r;
      try {
        r = await api.get(`/api/reports/${encodeURIComponent(id)}`);
      } catch (e) {
        if (cancelled) return;
        if (isAuthError(e)) {
          navigate('/admin/login', { replace: true });
          return;
        }
        if (e.status === 404) {
          setFatal({ code: 'not_found', message: 'Report not found.' });
        } else {
          setFatal({ code: e.code || 'error', message: e.message || 'Could not load report.' });
        }
        setLoading(false);
        return;
      }
      if (cancelled) return;
      setReport(r);
      setLoading(false);

      // Trend fetch (best-effort, same kind, last 8).
      try {
        const t = await api.get(`/api/reports?kind=${encodeURIComponent(r.kind)}&limit=8`);
        if (cancelled) return;
        const items = Array.isArray(t?.items) ? t.items : [];
        setTrend(items.slice().reverse());
      } catch (_) {
        setTrend([]);
      }
    }

    go();
    return () => { cancelled = true; };
  }, [id, navigate]);

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

  if (loading || !report) {
    return (
      <div style={{ padding: '48px 32px', color: 'var(--sb-fg-5)',
        fontFamily: 'var(--sb-font-mono)', fontSize: 12 }}>
        {'loading report\u2026'}
      </div>
    );
  }

  function handleCompare() {
    // Find previous report of same kind (in trend, oldest-first).
    const idx = trend.findIndex((r) => r.id === report.id);
    const prev = idx > 0 ? trend[idx - 1] : (trend[0]?.id !== report.id ? trend[trend.length - 1] : null);
    if (!prev) {
      toast.info('Need at least two reports of this kind to compare. Generate another to unlock.');
      return;
    }
    navigate(`/admin/reports/compare?a=${report.id}&b=${prev.id}`);
  }

  function handleAskLara() {
    openDrawer({
      prompt: `Summarize the key changes in this report (id: ${report.id}) and call out anything that needs attention.`,
      reports: [report],
    });
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1100 }}>
      <div style={{ marginBottom: 14 }}>
        <SBButton variant="ghost" size="xs" icon="arrow" onClick={() => navigate('/admin/reports')}>
          All reports
        </SBButton>
      </div>
      <ReportView
        report={report}
        trendReports={trend}
        onCompare={handleCompare}
        onAskLara={handleAskLara}
      />
    </div>
  );
}
