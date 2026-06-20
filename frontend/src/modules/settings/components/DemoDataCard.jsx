import React, { useState } from 'react';
import { SBButton, SBCard, SBChip } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../../leads/lib/toast.jsx';

// One-click sample data for new users — drop 12 fake leads across
// scores/sources so the user can play with Inbox, Leads, Accounts,
// Reports without connecting any real source. source='demo' means
// the wipe is a single DELETE.

export default function DemoDataCard() {
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    try {
      const r = await api.post('/api/workspace/settings/demo-data/load');
      toast.success(`${r.inserted} sample leads added${r.skipped ? ` · ${r.skipped} already present` : ''}`);
    } catch (err) {
      toast.error(err?.message || 'Could not load demo data');
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    if (!window.confirm('Wipe all demo leads? Leads with source != "demo" are untouched.')) return;
    setBusy(true);
    try {
      await api.delete('/api/workspace/settings/demo-data');
      toast.info('Demo leads removed');
    } catch (err) {
      toast.error(err?.message || 'Could not clear demo data');
    } finally {
      setBusy(false);
    }
  };

  return (
    <SBCard style={{ padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Sample data</span>
            <SBChip tone="muted">12 leads</SBChip>
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', lineHeight: 1.5 }}>
            Loads 12 fake leads across multiple scores, sources, and triggers
            so you can try the inbox / drawer / accounts / reports flows
            without connecting a real source. All carry source="demo" so
            removal is one click.
          </div>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <SBButton variant="primary" size="sm" icon="plus" disabled={busy} onClick={load}>
          {busy ? '…' : 'Load sample data'}
        </SBButton>
        <SBButton variant="ghost" size="sm" icon="close" disabled={busy} onClick={clear}>
          Wipe
        </SBButton>
      </div>
    </SBCard>
  );
}
