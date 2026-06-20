import React, { useState } from 'react';
import { SBButton, SBCard, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../../leads/lib/toast.jsx';

// DNS health check for the user's sending domain. Pure DNS lookups, no
// authentication required — anyone could `dig` the same records. Surfaces
// SPF / DKIM / DMARC / MX with a pass-warn-fail badge per record and a
// suggested fix when something is missing.
//
// Why this card exists: Google + Microsoft tightened bulk-sender enforcement
// in late 2025, so sending from a domain without these records correctly
// configured now routes most messages straight to spam. Most SDRs don't
// know if their setup is right; this gives them a clear go/no-go before
// they hit send. The trend scan calls this an enforcement line, not a
// nice-to-have.

const TONE = { pass: 'accent', warn: 'warm', fail: 'hot', unknown: 'muted' };
const ICON = { pass: 'check', warn: 'spark', fail: 'close', unknown: 'dot' };

export default function DnsHealthCard() {
  const [domain, setDomain] = useState('');
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null); // {domain, overall, checks}

  const run = async () => {
    const d = domain.trim().toLowerCase();
    if (!d || !d.includes('.')) {
      toast.error('Enter a domain like yourcompany.com');
      return;
    }
    setBusy(true);
    try {
      const r = await api.post('/api/workspace/settings/dns-check', { domain: d });
      setReport(r);
      const t = { pass: 'success', warn: 'info', fail: 'error' }[r.overall] || 'info';
      toast[t](`DNS check · ${r.overall.toUpperCase()}`);
    } catch (err) {
      toast.error(err?.details?.message || err?.message || 'DNS check failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <SBCard style={{ padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Sending domain · DNS health</span>
            {report && (
              <SBChip
                tone={TONE[report.overall] || 'muted'}
                icon={ICON[report.overall] || 'dot'}
              >{report.overall}</SBChip>
            )}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', lineHeight: 1.5 }}>
            Google + Microsoft enforce SPF / DKIM / DMARC + 1-click unsubscribe on bulk
            senders in 2026. A single missing record routes most outbound to spam.
            Run this before you send your first sequence.
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
        <input
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') run(); }}
          placeholder="yourcompany.com"
          style={{
            flex: 1, boxSizing: 'border-box',
            background: 'var(--sb-panel)', color: 'var(--sb-fg)',
            border: '1px solid var(--sb-line-2)', padding: '8px 12px',
            fontSize: 12.5, fontFamily: 'var(--sb-font-mono)', outline: 'none',
          }}
        />
        <SBButton variant="primary" size="sm" icon="bolt" disabled={busy} onClick={run}>
          {busy ? 'Checking…' : 'Run check'}
        </SBButton>
      </div>

      {report && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 14 }}>
          <CheckRow label="SPF"   check={report.checks.spf} />
          <CheckRow label="DKIM"  check={report.checks.dkim} />
          <CheckRow label="DMARC" check={report.checks.dmarc} />
          <CheckRow label="MX"    check={report.checks.mx} />
        </div>
      )}
    </SBCard>
  );
}

function CheckRow({ label, check }) {
  const status = check?.status || 'unknown';
  const tone = TONE[status] || 'muted';
  return (
    <div style={{
      borderTop: '1px solid var(--sb-line)', paddingTop: 10,
      display: 'grid', gridTemplateColumns: '70px 90px 1fr', gap: 10, alignItems: 'baseline',
    }}>
      <span style={{
        fontFamily: 'var(--sb-font-mono)', fontSize: 11.5, color: 'var(--sb-fg-3)',
        textTransform: 'uppercase', letterSpacing: '0.06em',
      }}>{label}</span>
      <SBChip tone={tone} icon={ICON[status] || 'dot'}>{status}</SBChip>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 12, color: 'var(--sb-fg-2)', lineHeight: 1.5 }}>
          {check?.detail || '—'}
        </div>
        {check?.fix && (
          <div style={{
            marginTop: 4, padding: '6px 10px',
            background: 'var(--sb-panel)', border: '1px solid var(--sb-line-2)',
            fontSize: 11.5, fontFamily: 'var(--sb-font-mono)', color: 'var(--sb-fg-3)',
            wordBreak: 'break-word',
          }}>
            <span style={{ color: 'var(--sb-fg-5)' }}>fix · </span>{check.fix}
          </div>
        )}
        {check?.record && (
          <div style={{
            marginTop: 4, fontSize: 10.5, color: 'var(--sb-fg-5)',
            fontFamily: 'var(--sb-font-mono)', wordBreak: 'break-all',
          }}>
            {Array.isArray(check.record) ? check.record.join(' / ') : check.record}
          </div>
        )}
        {check?.records && Array.isArray(check.records) && (
          <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {check.records.map((r) => (
              <div key={`${r.priority}-${r.host}`} style={{
                fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
              }}>
                {String(r.priority).padStart(2, ' ')} · {r.host}
              </div>
            ))}
          </div>
        )}
        {check?.selector && status === 'pass' && (
          <div style={{ marginTop: 2, fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
            selector · {check.selector}
          </div>
        )}
      </div>
    </div>
  );
}
