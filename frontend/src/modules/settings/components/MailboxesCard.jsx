import React, { useEffect, useState } from 'react';
import { SBButton, SBCard, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../../leads/lib/toast.jsx';

// Multi-mailbox SMTP routing card on /admin/settings.
// State: list of connected mailboxes + an inline form for adding a new
// one (provider preset → fill creds → Test → Save). The scheduler picks
// among enabled mailboxes round-robin with daily volume caps.
//
// Why this card exists: the trend scan flagged multi-domain routing as the
// feature that takes a sender from "demo" to "trustworthy at volume" —
// without it, sending 100+ emails/day from one inbox burns its reputation
// in 4-6 weeks. This is the MVP: own the rotation mechanics; users keep
// using their own warmup network (Mailreach/Warmup Inbox) on top.

const PRESETS = {
  gmail:    { host: 'smtp.gmail.com',         port: 587, use_tls: true,
              hint: 'Gmail / Workspace — needs an App Password if 2FA is on.' },
  outlook:  { host: 'smtp.office365.com',     port: 587, use_tls: true,
              hint: 'Outlook / Microsoft 365.' },
  fastmail: { host: 'smtp.fastmail.com',      port: 587, use_tls: true,
              hint: 'Fastmail.' },
  custom:   { host: '',                       port: 587, use_tls: true,
              hint: 'Custom SMTP server.' },
};

const empty = () => ({
  preset: 'gmail',
  email: '',
  from_name: '',
  host: PRESETS.gmail.host,
  port: PRESETS.gmail.port,
  username: '',
  password: '',
  use_tls: true,
  daily_send_cap: 50,
});

export default function MailboxesCard() {
  const [items, setItems] = useState(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [verified, setVerified] = useState(null);  // snapshot of creds that just passed Test

  const refresh = async () => {
    try {
      const r = await api.get('/api/workspace/settings/mailboxes', { fresh: true });
      setItems(r?.items || []);
    } catch (err) {
      toast.error(err?.message || 'Could not load mailboxes');
      setItems([]);
    }
  };
  useEffect(() => { refresh(); }, []);

  const onPreset = (k) => {
    const p = PRESETS[k];
    setForm((f) => ({ ...f, preset: k, host: p.host, port: p.port, use_tls: p.use_tls }));
  };

  const onTest = async () => {
    setBusy(true); setTestResult(null); setVerified(null);
    try {
      const r = await api.post('/api/workspace/settings/mailboxes/test', {
        host: form.host, port: form.port, username: form.username || form.email,
        password: form.password, use_tls: form.use_tls,
      });
      setTestResult(r);
      if (r.ok) {
        setVerified({
          host: form.host, port: form.port,
          username: form.username || form.email,
          password: form.password, use_tls: form.use_tls,
        });
        toast.success('SMTP login OK');
      } else {
        toast.error(r.error || 'SMTP test failed');
      }
    } catch (err) {
      const msg = err?.details?.error || err?.message || 'Test failed';
      setTestResult({ ok: false, error: msg });
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const onAdd = async () => {
    setBusy(true);
    try {
      await api.post('/api/workspace/settings/mailboxes', {
        email: form.email,
        from_name: form.from_name || null,
        host: form.host, port: form.port,
        username: form.username || form.email,
        password: form.password,
        use_tls: form.use_tls,
        daily_send_cap: form.daily_send_cap,
      });
      toast.success(`Added · ${form.email}`);
      setAdding(false);
      setForm(empty());
      setTestResult(null);
      setVerified(null);
      await refresh();
    } catch (err) {
      toast.error(err?.details?.message || err?.message || 'Add failed');
    } finally {
      setBusy(false);
    }
  };

  const onToggle = async (mb) => {
    try {
      await api.patch(`/api/workspace/settings/mailboxes/${mb.id}`, {
        enabled: !mb.enabled,
      });
      await refresh();
    } catch (err) {
      toast.error(err?.message || 'Toggle failed');
    }
  };

  const onDelete = async (mb) => {
    if (!window.confirm(`Remove ${mb.email}? In-flight sequences will fall back to other mailboxes (or Resend).`)) return;
    try {
      await api.delete(`/api/workspace/settings/mailboxes/${mb.id}`);
      toast.info('Mailbox removed');
      await refresh();
    } catch (err) {
      toast.error(err?.message || 'Delete failed');
    }
  };

  const onCapChange = async (mb, next) => {
    if (next === mb.daily_send_cap) return;
    try {
      await api.patch(`/api/workspace/settings/mailboxes/${mb.id}`, {
        daily_send_cap: next,
      });
      await refresh();
    } catch (err) {
      toast.error(err?.message || 'Cap update failed');
    }
  };

  // True when the form's creds match the snapshot that just tested OK.
  const isVerified = verified
    && verified.host === form.host && verified.port === form.port
    && verified.username === (form.username || form.email)
    && verified.password === form.password
    && verified.use_tls === form.use_tls;

  return (
    <SBCard style={{ padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Sending mailboxes</span>
            <SBChip tone="muted">{(items || []).length}</SBChip>
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', lineHeight: 1.5 }}>
            Outbound rotates across these inboxes with per-mailbox daily caps —
            sending 100+ from one address flags it within weeks. Empty list
            falls back to Resend single-domain. Recommended cap: 30-50/day per
            inbox (per the May-2026 deliverability scan).
          </div>
        </div>
        {!adding && (
          <SBButton variant="ghost" size="xs" icon="plus" onClick={() => setAdding(true)}>
            Add mailbox
          </SBButton>
        )}
      </div>

      {/* Existing mailboxes */}
      {items && items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {items.map((m) => (
            <MailboxRow key={m.id} m={m}
              onToggle={() => onToggle(m)}
              onDelete={() => onDelete(m)}
              onCapChange={(v) => onCapChange(m, v)} />
          ))}
        </div>
      )}

      {items && items.length === 0 && !adding && (
        <div style={{
          padding: '14px 16px', fontSize: 12, color: 'var(--sb-fg-5)',
          fontFamily: 'var(--sb-font-mono)', textAlign: 'center',
          border: '1px dashed var(--sb-line-2)',
        }}>
          ▸ no mailboxes yet — sending falls back to Resend
        </div>
      )}

      {/* Add form */}
      {adding && (
        <div style={{
          marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--sb-line)',
          display: 'flex', flexDirection: 'column', gap: 12,
        }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {Object.entries(PRESETS).map(([k]) => (
              <button key={k} onClick={() => onPreset(k)}
                style={{
                  padding: '5px 10px',
                  background: form.preset === k ? 'var(--sb-accent-bg)' : 'transparent',
                  border: `1px solid ${form.preset === k ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
                  color: form.preset === k ? 'var(--sb-accent)' : 'var(--sb-fg-3)',
                  cursor: 'pointer', fontSize: 11,
                  fontFamily: 'var(--sb-font-mono)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                }}>{k}</button>
            ))}
          </div>
          <div style={{ fontSize: 11, color: 'var(--sb-fg-5)' }}>
            {PRESETS[form.preset]?.hint}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
            <Field label="Email">
              <input value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value, username: form.username || e.target.value })}
                placeholder="you@yourdomain.com" style={inputMono} />
            </Field>
            <Field label="From name">
              <input value={form.from_name}
                onChange={(e) => setForm({ ...form, from_name: e.target.value })}
                placeholder="Kartik from Zerotoprod" style={inputMono} />
            </Field>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
            <Field label="SMTP host">
              <input value={form.host}
                onChange={(e) => setForm({ ...form, host: e.target.value })}
                placeholder="smtp.gmail.com" style={inputMono} />
            </Field>
            <Field label="Port">
              <input type="number" value={form.port}
                onChange={(e) => setForm({ ...form, port: parseInt(e.target.value, 10) || 587 })}
                style={inputMono} />
            </Field>
          </div>

          <Field label="App password" hint="Gmail: create an App Password in your Google account.">
            <input type="password" value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="16-character app password" style={inputMono} />
          </Field>

          <Field label="Daily send cap" hint="Per-mailbox daily ceiling. 30-50 is the safe band.">
            <input type="number" min={1} max={2000} value={form.daily_send_cap}
              onChange={(e) => setForm({ ...form, daily_send_cap: Math.max(1, Math.min(2000, parseInt(e.target.value, 10) || 50)) })}
              style={inputMono} />
          </Field>

          {testResult && (
            <div style={{
              padding: '10px 12px', fontSize: 12, fontFamily: 'var(--sb-font-mono)',
              background: testResult.ok ? 'var(--sb-accent-bg)' : 'var(--sb-hot-bg)',
              border: `1px solid ${testResult.ok ? 'var(--sb-accent)' : 'var(--sb-hot)'}`,
              color: testResult.ok ? 'var(--sb-accent)' : 'var(--sb-hot)',
            }}>
              {testResult.ok ? '▸ SMTP login OK' : `▸ ${testResult.error}`}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            <SBButton variant="ghost" size="sm" onClick={() => { setAdding(false); setForm(empty()); setTestResult(null); }}>
              Cancel
            </SBButton>
            <SBButton variant="ghost" size="sm" icon="bolt"
              disabled={busy || !form.host || !form.email || !form.password}
              onClick={onTest}>
              Test connection
            </SBButton>
            <SBButton variant="primary" size="sm" icon="check"
              disabled={busy || !isVerified || !form.email}
              title={isVerified ? 'Save these creds' : 'Run "Test connection" first'}
              onClick={onAdd}>
              {busy ? 'Saving…' : 'Add mailbox'}
            </SBButton>
          </div>
        </div>
      )}
    </SBCard>
  );
}

function MailboxRow({ m, onToggle, onDelete, onCapChange }) {
  const [editingCap, setEditingCap] = useState(false);
  const [capDraft, setCapDraft] = useState(m.daily_send_cap);
  const pct = Math.min(100, Math.round(((m.sent_today || 0) / (m.daily_send_cap || 1)) * 100));
  const exhausted = (m.sent_today || 0) >= (m.daily_send_cap || 0);

  return (
    <div style={{
      padding: '12px 14px', border: '1px solid var(--sb-line-2)', background: 'var(--sb-card)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <SBIcon name="at" size={12} stroke={1.6} />
        <span style={{ fontSize: 13, fontWeight: 600 }}>{m.email}</span>
        {m.from_name && (
          <span style={{ fontSize: 11.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
            · {m.from_name}
          </span>
        )}
        <div style={{ flex: 1 }} />
        {m.enabled
          ? <SBChip tone="accent" icon="dot">enabled</SBChip>
          : <SBChip tone="muted">paused</SBChip>}
        {m.last_error && <SBChip tone="hot">error</SBChip>}
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: '1fr auto', gap: 10, alignItems: 'center',
      }}>
        <div>
          <div style={{
            position: 'relative', height: 6, background: 'var(--sb-line-2)',
          }}>
            <div style={{
              position: 'absolute', inset: 0, width: `${pct}%`,
              background: exhausted ? 'var(--sb-hot)' : pct > 80 ? 'var(--sb-warm)' : 'var(--sb-accent)',
              transition: 'width 240ms',
            }} />
          </div>
          <div style={{
            marginTop: 4, fontSize: 10.5, color: 'var(--sb-fg-5)',
            fontFamily: 'var(--sb-font-mono)',
          }}>
            {m.sent_today || 0} / {editingCap ? (
              <input type="number" min={1} max={2000} value={capDraft} autoFocus
                onChange={(e) => setCapDraft(Math.max(1, Math.min(2000, parseInt(e.target.value, 10) || 1)))}
                onBlur={() => { onCapChange(capDraft); setEditingCap(false); }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { onCapChange(capDraft); setEditingCap(false); }
                  if (e.key === 'Escape') { setCapDraft(m.daily_send_cap); setEditingCap(false); }
                }}
                style={{
                  width: 60, background: 'var(--sb-panel)', color: 'var(--sb-accent)',
                  border: '1px solid var(--sb-line-2)', padding: '1px 4px',
                  fontSize: 10.5, fontFamily: 'var(--sb-font-mono)', outline: 'none',
                }}
              />
            ) : (
              <span onClick={() => { setEditingCap(true); setCapDraft(m.daily_send_cap); }}
                style={{ cursor: 'pointer', textDecoration: 'underline dotted' }}
                title="Click to edit cap">
                {m.daily_send_cap}
              </span>
            )} sent today · {Math.max(0, (m.daily_send_cap || 0) - (m.sent_today || 0))} headroom
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <SBButton variant="ghost" size="xs" onClick={onToggle}>
            {m.enabled ? 'Pause' : 'Enable'}
          </SBButton>
          <SBButton variant="ghost" size="xs" icon="close" onClick={onDelete}>
            Remove
          </SBButton>
        </div>
      </div>

      {m.last_error && (
        <div style={{
          marginTop: 8, padding: '6px 10px',
          background: 'var(--sb-hot-bg)', border: '1px solid var(--sb-hot)',
          color: 'var(--sb-hot)', fontSize: 11, fontFamily: 'var(--sb-font-mono)',
        }}>
          {m.last_error}
        </div>
      )}
    </div>
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
      {hint && <div style={{ marginTop: 3, fontSize: 11, color: 'var(--sb-fg-5)' }}>{hint}</div>}
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
