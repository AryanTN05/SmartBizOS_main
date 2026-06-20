import React, { useEffect, useState } from 'react';
import { SBButton, SBCard, SBIcon } from '../../components/primitives';
import api from '../../lib/api.js';
import { toast } from '../../modules/leads/lib/toast.jsx';
import IcpWizard from '../../modules/settings/components/IcpWizard.jsx';
import ImapSettingsCard from '../../modules/settings/components/ImapSettingsCard.jsx';
import DnsHealthCard from '../../modules/settings/components/DnsHealthCard.jsx';
import MailboxesCard from '../../modules/settings/components/MailboxesCard.jsx';
import SuppressionsCard from '../../modules/settings/components/SuppressionsCard.jsx';
import DemoDataCard from '../../modules/settings/components/DemoDataCard.jsx';

// /admin/settings — workspace-level config. Currently:
//   - icp_description  — interpolated into the LLM ICP scorer's system
//                         prompt; tunes scoring per-workspace
//   - workspace_name   — display name (used in outbound emails)
//   - sender_name      — sender identity for Resend
//
// Saving a non-empty icp_description changes the score reasoning on the
// next enrichment pass. Empty (= reset) falls back to the in-code default.
export default function Settings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // The wizard hijacks the ICP card whenever icp_description is empty (new
  // user) or when the user explicitly clicks "Re-run wizard." The plain
  // textarea remains the default for users who already have an ICP saved.
  const [forceWizard, setForceWizard] = useState(false);
  const [form, setForm] = useState({
    icp_description: '',
    workspace_name: '',
    sender_name: '',
    slack_webhook_url: '',
    slack_alert_min_score: 80,
    send_time_optimization: false,
    calendar_link: '',
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get('/api/workspace/settings', { fresh: true });
        if (cancelled) return;
        setForm({
          icp_description: r?.icp_description || '',
          workspace_name: r?.workspace_name || '',
          sender_name: r?.sender_name || '',
          slack_webhook_url: r?.slack_webhook_url || '',
          slack_alert_min_score: r?.slack_alert_min_score ?? 80,
          send_time_optimization: !!r?.send_time_optimization,
          calendar_link: r?.calendar_link || '',
        });
      } catch (err) {
        if (err.status === 401) { window.location.href = '/admin/login'; return; }
        toast.error(err.message || 'Could not load settings.');
      } finally {
        setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const r = await api.patch('/api/workspace/settings', form);
      setForm({
        icp_description: r?.icp_description || '',
        workspace_name: r?.workspace_name || '',
        sender_name: r?.sender_name || '',
        slack_webhook_url: r?.slack_webhook_url || '',
        slack_alert_min_score: r?.slack_alert_min_score ?? 80,
      });
      toast.success('Saved · scoring will use this on the next enrichment');
    } catch (err) {
      toast.error(err.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ padding: '28px 32px', maxWidth: 760 }}>
      <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 6 }}>Workspace</div>
      <h1 style={{ fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 600, margin: 0, letterSpacing: '-0.02em' }}>
        Settings
      </h1>
      <p style={{ marginTop: 10, color: 'var(--sb-fg-4)', fontSize: 13, lineHeight: 1.6, maxWidth: 560 }}>
        Tune Lara's scoring + outbound identity for your workspace. The ICP
        description is interpolated into the LLM scorer's system prompt — it's
        the single highest-leverage knob you have here.
      </p>

      {loading ? (
        <div style={{ marginTop: 28, color: 'var(--sb-fg-5)', fontSize: 12, fontFamily: 'var(--sb-font-mono)' }}>
          ▸ loading…
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18, marginTop: 28 }}>
          {/* ICP card — wizard or plain textarea depending on state. */}
          {(!form.icp_description || forceWizard) ? (
            <IcpWizard
              initialIcp={form.icp_description}
              onSaved={(saved) => {
                setForm((f) => ({ ...f, icp_description: saved }));
                setForceWizard(false);
              }}
              onCancel={forceWizard ? () => setForceWizard(false) : undefined}
            />
          ) : (
            <SBCard style={{ padding: 22 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <Label
                    title="Ideal Customer Profile"
                    hint="The single highest-leverage knob. Edit freely or re-run the wizard from a different archetype."
                  />
                </div>
                <button
                  onClick={() => {
                    if (window.confirm('Re-run the wizard? Your current ICP stays in place until you save in the wizard.')) {
                      setForceWizard(true);
                    }
                  }}
                  style={{
                    background: 'transparent', border: '1px solid var(--sb-line-2)',
                    color: 'var(--sb-fg-3)', cursor: 'pointer',
                    padding: '5px 10px', fontSize: 11,
                    fontFamily: 'var(--sb-font-mono)',
                    textTransform: 'uppercase', letterSpacing: '0.08em',
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                  }}
                  title="Re-run the 3-step wizard"
                >
                  <SBIcon name="spark" size={11} stroke={1.5} />
                  Re-run wizard
                </button>
              </div>
              <textarea
                value={form.icp_description}
                onChange={(e) => setForm({ ...form, icp_description: e.target.value })}
                rows={9}
                maxLength={4000}
                placeholder={'Segment: B2B SaaS or e-commerce\nHeadcount: 10-500\nRevenue: >$1M ARR, pre-Series-C\nPain: spreadsheets, no RevOps\nDisqualifiers: <10 employees, NGO, consumer'}
                style={{
                  width: '100%', boxSizing: 'border-box', marginTop: 10,
                  background: 'var(--sb-panel)', color: 'var(--sb-fg)',
                  border: '1px solid var(--sb-line-2)', padding: '10px 12px',
                  fontSize: 13, fontFamily: 'var(--sb-font-mono)', lineHeight: 1.7,
                  resize: 'vertical',
                }}
              />
              <div style={{
                marginTop: 6, fontSize: 11, color: 'var(--sb-fg-5)',
                fontFamily: 'var(--sb-font-mono)', textAlign: 'right',
              }}>
                {form.icp_description.length} / 4000
              </div>
            </SBCard>
          )}

          <SBCard style={{ padding: 22, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <Label title="Workspace name" hint="Display name. Shows in headers + outbound emails." />
              <input
                value={form.workspace_name}
                onChange={(e) => setForm({ ...form, workspace_name: e.target.value })}
                placeholder="e.g. Zerotoprod"
                style={inputStyle}
              />
            </div>
            <div>
              <Label title="Sender name" hint="From-name on outbound emails sent by automations." />
              <input
                value={form.sender_name}
                onChange={(e) => setForm({ ...form, sender_name: e.target.value })}
                placeholder="e.g. Kartik from Zerotoprod"
                style={inputStyle}
              />
            </div>
          </SBCard>

          <SBCard style={{ padding: 22 }}>
            <Label
              title="Calendar booking link"
              hint="Cal.com / Calendly / HubSpot Meetings / SavvyCal URL. Auto-injected as a soft CTA in AI-drafted replies. Empty = no link."
            />
            <input
              value={form.calendar_link}
              onChange={(e) => setForm({ ...form, calendar_link: e.target.value })}
              placeholder="https://cal.com/yourname/15min"
              style={{ ...inputStyle, fontFamily: 'var(--sb-font-mono)', fontSize: 12 }}
            />
          </SBCard>

          <SBCard style={{ padding: 22, display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
            <div>
              <Label
                title="Slack webhook for hot leads"
                hint="Paste an incoming-webhook URL from Slack. SmartBiz POSTs a compact lead summary the moment a scraper produces a high-fit lead. Empty = no alerts."
              />
              <input
                value={form.slack_webhook_url}
                onChange={(e) => setForm({ ...form, slack_webhook_url: e.target.value })}
                placeholder="https://hooks.slack.com/services/T0/B0/xxxxxxxxxxxxxxxxxxxxxxxx"
                style={{ ...inputStyle, fontFamily: 'var(--sb-font-mono)', fontSize: 12 }}
              />
            </div>
            <div>
              <Label title="Min score" hint="Threshold to alert on (0-100)." />
              <input
                type="number" min={0} max={100}
                value={form.slack_alert_min_score}
                onChange={(e) => setForm({ ...form, slack_alert_min_score: Math.max(0, Math.min(100, parseInt(e.target.value, 10) || 0)) })}
                style={inputStyle}
              />
            </div>
          </SBCard>

          <SBCard style={{ padding: 22, display: 'flex', alignItems: 'flex-start', gap: 14 }}>
            <div style={{ flex: 1 }}>
              <Label
                title="Send-time optimization"
                hint="Queue new sequence sends at the prospect's likely 9-11 AM local instead of immediately. Heuristic timezone via email TLD or company domain. Weekends bump to Monday morning."
              />
            </div>
            <button
              onClick={() => setForm({ ...form, send_time_optimization: !form.send_time_optimization })}
              style={{
                position: 'relative', width: 44, height: 24, padding: 2,
                background: form.send_time_optimization ? 'var(--sb-accent)' : 'var(--sb-line-2)',
                border: 'none', cursor: 'pointer', borderRadius: 14,
                transition: 'background 160ms', flexShrink: 0,
              }}
              aria-label="Toggle send-time optimization"
            >
              <span style={{
                position: 'absolute', top: 2,
                left: form.send_time_optimization ? 22 : 2,
                width: 20, height: 20,
                background: 'var(--sb-bg)', borderRadius: 10,
                transition: 'left 160ms',
              }} />
            </button>
          </SBCard>

          <ImapSettingsCard />

          <MailboxesCard />

          <DnsHealthCard />

          <SuppressionsCard />

          <DemoDataCard />

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <SBButton variant="primary" size="sm" icon="check"
              disabled={saving} onClick={save}>
              {saving ? 'Saving…' : 'Save settings'}
            </SBButton>
          </div>
        </div>
      )}
    </div>
  );
}

function Label({ title, hint }) {
  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{title}</div>
      {hint && (
        <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', lineHeight: 1.5 }}>{hint}</div>
      )}
    </div>
  );
}

const inputStyle = {
  width: '100%', boxSizing: 'border-box', marginTop: 10,
  background: 'var(--sb-panel)', color: 'var(--sb-fg)',
  border: '1px solid var(--sb-line-2)', padding: '8px 12px',
  fontSize: 13, fontFamily: 'var(--sb-font)',
};
