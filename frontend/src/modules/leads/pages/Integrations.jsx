import React, { useCallback, useEffect, useState } from 'react';
import { SBButton, SBCard, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../lib/toast.jsx';

// /admin/integrations — roadmap surface. OAuth adapters for HubSpot / Zoho /
// Sheets / Tally aren't implemented yet; the page shows what's coming and
// lets users disconnect any pre-existing rows from earlier demo seeds. The
// previous "Connect" path shortcut to status='connected' without any auth
// — pulled out so the UI doesn't lie about state that doesn't exist.

const PROVIDER_LABELS = {
  hubspot: 'HubSpot',
  zoho: 'Zoho',
  sheets: 'Google Sheets',
  tally: 'Tally',
};

const PROVIDER_BLURB = {
  hubspot: 'Two-way sync of contacts, deals and pipeline stage.',
  zoho: 'Two-way sync. Pipeline stage mapping included.',
  sheets: 'Pull leads from a configured Google Sheet.',
  tally: 'Pull form submissions as leads (seeded in V0).',
};

export default function Integrations() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirmDc, setConfirmDc] = useState(null); // integration obj

  const fetchList = useCallback(async () => {
    try {
      const res = await api.get('/api/integrations');
      setItems(res.items || []);
    } catch (err) {
      if (err.status === 401) {
        window.location.href = '/admin/login';
      } else {
        toast.error(err.message || 'Could not load integrations.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  const disconnect = async (integration) => {
    try {
      await api.post(`/api/integrations/${integration.id}/disconnect`);
      toast.success(`${PROVIDER_LABELS[integration.provider] || integration.provider} disconnected`);
      setConfirmDc(null);
      fetchList();
    } catch (err) {
      toast.error(err.message || 'Disconnect failed');
    }
  };

  return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{ marginBottom: 20 }}>
        <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 8 }}>Roadmap · Integrations</div>
        <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 30, fontWeight: 600, margin: 0, letterSpacing: '-0.02em' }}>
          Keep your existing CRM. <span style={{ color: 'var(--sb-fg-5)' }}>We'll make it smarter.</span>
        </h1>
        <p style={{ marginTop: 10, color: 'var(--sb-fg-4)', fontSize: 13, lineHeight: 1.6, maxWidth: 560 }}>
          OAuth adapters are on the roadmap — we'd rather show that honestly
          than fake a "Connected" badge. Until each provider ships, the page
          below is a preview of what's coming. IMAP reply-detection is real
          and lives on the Settings page.
        </p>
      </div>

      {loading && items.length === 0 ? (
        <div style={{ padding: 24, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
          ▸ loading…
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 14 }}>
          {items.map((it) => (
            <SBCard key={it.id} style={{ padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <div style={{
                  width: 32, height: 32, background: 'var(--sb-panel)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: 'var(--sb-accent)', border: '1px solid var(--sb-line-2)',
                }}>
                  <SBIcon name="at" size={14} stroke={1.6} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>
                    {PROVIDER_LABELS[it.provider] || it.provider}
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', fontFamily: 'var(--sb-font-mono)' }}>
                    {it.connected_account_label || '—'}
                  </div>
                </div>
                <StatusChip status={it.status} />
              </div>

              <p style={{ margin: '8px 0 14px', fontSize: 12.5, color: 'var(--sb-fg-4)', lineHeight: 1.55 }}>
                {PROVIDER_BLURB[it.provider] || ''}
              </p>

              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {it.status === 'connected' ? (
                  <SBButton variant="ghost" size="sm" icon="close" onClick={() => setConfirmDc(it)}>
                    Disconnect
                  </SBButton>
                ) : (
                  <SBButton
                    variant="ghost" size="sm" icon="clock" disabled
                    title="OAuth adapter not implemented yet"
                  >
                    Coming soon
                  </SBButton>
                )}
              </div>
            </SBCard>
          ))}
        </div>
      )}

      {confirmDc && (
        <ConfirmModal
          title={`Disconnect ${PROVIDER_LABELS[confirmDc.provider] || confirmDc.provider}?`}
          body="Revokes stored tokens. Previously-synced leads remain in your DB."
          danger
          onCancel={() => setConfirmDc(null)}
          onConfirm={() => disconnect(confirmDc)}
        />
      )}
    </div>
  );
}

function StatusChip({ status }) {
  if (status === 'connected') return <SBChip tone="accent" icon="dot">connected</SBChip>;
  return <SBChip tone="muted">coming soon</SBChip>;
}

function ConfirmModal({ title, body, onConfirm, onCancel, danger }) {
  return (
    <>
      <div onClick={onCancel} style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 40,
      }} />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        width: 380, background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-2)',
        padding: 24, zIndex: 45,
      }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>{title}</div>
        <div style={{ fontSize: 12.5, color: 'var(--sb-fg-4)', marginBottom: 16, lineHeight: 1.55 }}>{body}</div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <SBButton variant="ghost" onClick={onCancel}>Cancel</SBButton>
          <SBButton variant={danger ? 'danger' : 'primary'} onClick={onConfirm}>
            {danger ? 'Disconnect' : 'Confirm'}
          </SBButton>
        </div>
      </div>
    </>
  );
}
