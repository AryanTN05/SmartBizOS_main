import React, { useEffect, useState } from 'react';
import { SBButton, SBCard, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../../leads/lib/toast.jsx';

// IMAP reply-detection settings card on /admin/settings.
// State machine:
//   not_configured  →  user fills form → Test → Save → configured
//   configured      →  show status + (Re-enter | Disconnect | Poll now)
//
// Password is encrypted server-side via Fernet (IMAP_ENCRYPTION_KEY env var)
// and never returned by GET — the FE only ever knows {configured, host,
// port, email, last_poll_at, last_error}.

const PRESETS = {
  gmail:    { host: 'imap.gmail.com',           port: 993, use_ssl: true,  hint: 'Gmail / Workspace — needs an App Password if 2FA is on.' },
  outlook:  { host: 'outlook.office365.com',    port: 993, use_ssl: true,  hint: 'Outlook / Microsoft 365.' },
  fastmail: { host: 'imap.fastmail.com',        port: 993, use_ssl: true,  hint: 'Fastmail.' },
  custom:   { host: '',                          port: 993, use_ssl: true,  hint: 'Custom IMAP server.' },
};

const formatRel = (unix) => {
  if (!unix) return null;
  const ms = Date.now() - unix * 1000;
  const m = Math.floor(ms / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
};

export default function ImapSettingsCard() {
  const [status, setStatus] = useState(null);  // {configured, ...} | null while loading
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    preset: 'gmail',
    host: PRESETS.gmail.host,
    port: PRESETS.gmail.port,
    email: '',
    password: '',
    use_ssl: true,
  });
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState(null); // {ok, unread?, error?}
  // Snapshot of the form values that produced testResult.ok = true. Save is
  // only allowed when the current form still matches this snapshot — i.e. the
  // same credentials we successfully connected with. Editing anything after a
  // good test invalidates it (forces a fresh Test before Save).
  const [verifiedSnapshot, setVerifiedSnapshot] = useState(null);

  useEffect(() => { refresh(); }, []);

  const refresh = async () => {
    try {
      const r = await api.get('/api/workspace/settings/imap', { fresh: true });
      setStatus(r);
      // If not configured, surface the form by default. If configured, hide it.
      if (!r?.configured) setEditing(true);
    } catch (err) {
      toast.error(err?.message || 'Could not load IMAP settings');
    }
  };

  const onPreset = (key) => {
    const p = PRESETS[key];
    setForm((f) => ({ ...f, preset: key, host: p.host, port: p.port, use_ssl: p.use_ssl }));
  };

  const onTest = async () => {
    setBusy(true); setTestResult(null); setVerifiedSnapshot(null);
    try {
      const r = await api.post('/api/workspace/settings/imap/test', {
        host: form.host, port: form.port, email: form.email,
        password: form.password, use_ssl: form.use_ssl,
      });
      setTestResult(r);
      if (r.ok) {
        // Lock the verified state to the exact creds that just worked. Save
        // will re-disable the moment any field changes.
        setVerifiedSnapshot({
          host: form.host, port: form.port, email: form.email,
          password: form.password, use_ssl: form.use_ssl,
        });
        toast.success(`Connected · ${r.unread} unread in INBOX`);
      } else {
        toast.error(r.error || 'Connection failed');
      }
    } catch (err) {
      const msg = err?.details?.message || err?.message || 'Test failed';
      setTestResult({ ok: false, error: msg });
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  // True when the form matches the credentials we last verified — i.e. Save
  // would persist the same creds the test succeeded against. Anything else
  // means the user edited a field after the test and needs to re-test.
  const isVerified = (() => {
    if (!verifiedSnapshot || !testResult?.ok) return false;
    const v = verifiedSnapshot;
    return v.host === form.host && v.port === form.port
      && v.email === form.email && v.password === form.password
      && v.use_ssl === form.use_ssl;
  })();

  const onSave = async () => {
    setBusy(true);
    try {
      await api.put('/api/workspace/settings/imap', {
        host: form.host, port: form.port, email: form.email,
        password: form.password, use_ssl: form.use_ssl,
      });
      toast.success('IMAP saved · poller will check every 10 min');
      setForm((f) => ({ ...f, password: '' }));  // clear from FE memory
      setVerifiedSnapshot(null);
      setTestResult(null);
      setEditing(false);
      await refresh();
    } catch (err) {
      toast.error(err?.details?.message || err?.message || 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const onDisconnect = async () => {
    if (!window.confirm('Disconnect IMAP? Replies will only flip via the manual button afterward.')) return;
    setBusy(true);
    try {
      await api.delete('/api/workspace/settings/imap');
      toast.info('IMAP disconnected');
      setEditing(true);
      setStatus({ configured: false });
    } catch (err) {
      toast.error(err?.message || 'Disconnect failed');
    } finally {
      setBusy(false);
    }
  };

  const onPollNow = async () => {
    setBusy(true);
    try {
      const r = await api.post('/api/workspace/settings/imap/poll-now');
      const summary = (r?.results || [])[0];
      if (summary) {
        toast.success(`Poll: scanned ${summary.scanned}, matched ${summary.matched}, skipped ${summary.skipped}`);
      } else {
        toast.info('Poll ran — no tenant rows configured');
      }
      await refresh();
    } catch (err) {
      toast.error(err?.message || 'Poll failed');
    } finally {
      setBusy(false);
    }
  };

  if (status === null) {
    return (
      <SBCard style={{ padding: 22 }}>
        <div style={{ color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', fontSize: 12 }}>
          ▸ loading IMAP settings…
        </div>
      </SBCard>
    );
  }

  return (
    <SBCard style={{ padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: editing ? 14 : 4 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Reply detection · IMAP</span>
            {status.configured ? (
              status.last_error
                ? <SBChip tone="hot">error</SBChip>
                : <SBChip tone="accent" icon="check">connected</SBChip>
            ) : (
              <SBChip tone="muted">not connected</SBChip>
            )}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', lineHeight: 1.5 }}>
            Polls your inbox every 10 min for replies. Matches by sender email
            and pauses the matching lead's sequence. App password only — not
            your account password.
          </div>
        </div>
        {status.configured && !editing && (
          <SBButton variant="ghost" size="xs" icon="spark"
            disabled={busy} onClick={onPollNow}>
            Poll now
          </SBButton>
        )}
      </div>

      {/* Configured + collapsed view */}
      {status.configured && !editing && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
          <KV k="email"        v={status.email} mono />
          <KV k="server"       v={`${status.host}:${status.port}${status.use_ssl ? ' · ssl' : ''}`} mono />
          <KV k="last poll"    v={formatRel(status.last_poll_at_unix) || '— never'} mono />
          {status.last_error && (
            <div style={{
              padding: '10px 12px', background: 'var(--sb-hot-bg)',
              border: '1px solid var(--sb-hot)', color: 'var(--sb-hot)', fontSize: 11.5,
              fontFamily: 'var(--sb-font-mono)',
            }}>
              {status.last_error}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <SBButton variant="ghost" size="xs"
              onClick={() => { setEditing(true); setForm((f) => ({ ...f, email: status.email, host: status.host, port: status.port, use_ssl: status.use_ssl, password: '' })); }}>
              Re-enter credentials
            </SBButton>
            <SBButton variant="ghost" size="xs" icon="close" onClick={onDisconnect} disabled={busy}>
              Disconnect
            </SBButton>
          </div>
        </div>
      )}

      {/* Editing form */}
      {editing && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {Object.entries(PRESETS).map(([k, p]) => (
              <button
                key={k} onClick={() => onPreset(k)}
                style={{
                  padding: '5px 10px',
                  background: form.preset === k ? 'var(--sb-accent-bg)' : 'transparent',
                  border: `1px solid ${form.preset === k ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
                  color: form.preset === k ? 'var(--sb-accent)' : 'var(--sb-fg-3)',
                  cursor: 'pointer',
                  fontSize: 11, fontFamily: 'var(--sb-font-mono)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                }}
              >{k}</button>
            ))}
          </div>
          <div style={{ fontSize: 11, color: 'var(--sb-fg-5)' }}>
            {PRESETS[form.preset]?.hint}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
            <Field label="IMAP host">
              <input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })}
                placeholder="imap.gmail.com" style={inputMono} />
            </Field>
            <Field label="Port">
              <input type="number" value={form.port}
                onChange={(e) => setForm({ ...form, port: parseInt(e.target.value, 10) || 993 })}
                style={inputMono} />
            </Field>
          </div>
          <Field label="Email address">
            <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="you@yourdomain.com" style={inputMono} />
          </Field>
          <Field label="App password" hint="Gmail: create an App Password in your Google account.">
            <input type="password" value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="16-character app password"
              style={inputMono} />
          </Field>

          {testResult && (
            <div style={{
              padding: '10px 12px', fontSize: 12, fontFamily: 'var(--sb-font-mono)',
              background: testResult.ok ? 'var(--sb-accent-bg)' : 'var(--sb-hot-bg)',
              border: `1px solid ${testResult.ok ? 'var(--sb-accent)' : 'var(--sb-hot)'}`,
              color: testResult.ok ? 'var(--sb-accent)' : 'var(--sb-hot)',
            }}>
              {testResult.ok
                ? `▸ connected · ${testResult.unread} unread in INBOX`
                : `▸ ${testResult.error}`}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            {status.configured && (
              <SBButton variant="ghost" size="sm" onClick={() => setEditing(false)}>
                Cancel
              </SBButton>
            )}
            <SBButton variant="ghost" size="sm" icon="bolt"
              disabled={busy || !form.host || !form.email || !form.password}
              onClick={onTest}>
              Test connection
            </SBButton>
            <SBButton variant="primary" size="sm" icon="check"
              disabled={busy || !isVerified}
              title={isVerified ? 'Save these credentials' : 'Run "Test connection" first'}
              onClick={onSave}>
              {busy ? 'Saving…' : 'Save'}
            </SBButton>
          </div>
        </div>
      )}
    </SBCard>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <div style={{
        fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
        textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4,
      }}>{label}</div>
      {children}
      {hint && (
        <div style={{ marginTop: 3, fontSize: 11, color: 'var(--sb-fg-5)' }}>{hint}</div>
      )}
    </div>
  );
}

function KV({ k, v, mono }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', gap: 12, fontSize: 12 }}>
      <span style={{ color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>{k}</span>
      <span style={{ color: 'var(--sb-fg-2)', fontFamily: mono ? 'var(--sb-font-mono)' : 'var(--sb-font)' }}>
        {v}
      </span>
    </div>
  );
}

const inputMono = {
  width: '100%', boxSizing: 'border-box',
  padding: '8px 12px',
  background: 'var(--sb-panel)', color: 'var(--sb-fg)',
  border: '1px solid var(--sb-line-2)',
  fontSize: 12.5, fontFamily: 'var(--sb-font-mono)',
  outline: 'none',
};
