// M3 Automation + M6 Reports.

const RUNS = [
  { id: "run_42", lead: "Priya Krishnan", co: "Rupee.co", template: "warm_v1", status: "running", step: 3, total: 6, started: "2d ago" },
  { id: "run_41", lead: "Deepak Reddy", co: "Stacklane", template: "cold_v1", status: "branched", step: 4, total: 5, started: "3d ago" },
  { id: "run_40", lead: "Rohan Shah", co: "Lendly", template: "warm_v1", status: "completed", step: 6, total: 6, started: "5d ago" },
  { id: "run_39", lead: "Nisha Varma", co: "Flux", template: "cold_v1", status: "failed", step: 2, total: 5, started: "5d ago" },
];

function AutomationView() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", height: "calc(100vh - 60px)" }}>
      <div style={{ borderRight: "1px solid var(--sb-line)", overflow: "auto" }}>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--sb-line)", display: "flex", alignItems: "center", gap: 8 }}>
          <span className="sb-label">Runs</span>
          <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 11, color: "var(--sb-fg-4)" }}>{RUNS.length}</span>
          <div style={{ flex: 1 }} />
          <SBButton variant="ghost" size="xs" icon="filter">Active</SBButton>
        </div>
        {RUNS.map((r, i) => <RunListItem key={r.id} r={r} active={i === 0} />)}
      </div>
      <RunDetail run={RUNS[0]} />
    </div>
  );
}
window.AutomationView = AutomationView;

function RunListItem({ r, active }) {
  const statusColor = { running: "var(--sb-accent)", branched: "var(--sb-warm)", completed: "var(--sb-lime)", failed: "var(--sb-hot)" }[r.status];
  return (
    <div style={{
      padding: "12px 20px", borderBottom: "1px solid var(--sb-line)",
      background: active ? "var(--sb-card)" : "transparent", cursor: "pointer",
      borderLeft: `2px solid ${active ? "var(--sb-accent)" : "transparent"}`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 11, color: "var(--sb-fg-5)" }}>{r.id}</span>
        <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 10, color: statusColor, textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 700 }}>{r.status}</span>
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--sb-fg)" }}>{r.lead}</div>
      <div style={{ fontSize: 11.5, color: "var(--sb-fg-4)", marginTop: 2, fontFamily: "var(--sb-font-mono)" }}>{r.template} · {r.step}/{r.total} · {r.started}</div>
      <div style={{ display: "flex", gap: 2, marginTop: 8 }}>
        {Array.from({ length: r.total }).map((_, i) => (
          <div key={i} style={{ flex: 1, height: 2, background: i < r.step ? statusColor : "var(--sb-line-2)" }} />
        ))}
      </div>
    </div>
  );
}

function RunDetail({ run }) {
  const steps = [
    { name: "load_lead", kind: "run", status: "done", ms: 42, result: "lead snapshot" },
    { name: "render_email_day0", kind: "run", status: "done", ms: 128, result: "warm_v1 · 342 tokens" },
    { name: "send_day0", kind: "run", status: "done", ms: 811, result: "resend · msg_a8f2…" },
    { name: "wait_3_days", kind: "sleep", status: "done", duration: "3d" },
    { name: "wait_open", kind: "wait_for_event", status: "active", duration: "2d remaining", detail: "waiting on email.opened" },
    { name: "branch", kind: "branch", status: "pending", detail: "→ follow_up OR breakup" },
    { name: "send_followup", kind: "run", status: "pending" },
  ];
  return (
    <div style={{ overflow: "auto", padding: 28 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
        <span className="sb-label" style={{ color: "var(--sb-accent)" }}>{run.id}</span>
        <SBChip tone="accent" icon="dot">Running</SBChip>
      </div>
      <h2 style={{ fontFamily: "var(--sb-font-display)", fontSize: 24, fontWeight: 600, margin: "0 0 4px", letterSpacing: "-0.02em" }}>
        {run.template} <span style={{ color: "var(--sb-fg-5)" }}>·</span> <span style={{ color: "var(--sb-fg-3)" }}>{run.lead}</span>
      </h2>
      <p style={{ fontSize: 13, color: "var(--sb-fg-4)", margin: "0 0 24px", fontFamily: "var(--sb-font-mono)" }}>
        inngest_run · fn_id: nurture.warm_v1 · started {run.started}
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 28 }}>
        <SBStat label="Step" value="3/6" mono />
        <SBStat label="Elapsed" value="2d 04h" mono />
        <SBStat label="Events" value="7" mono />
        <SBStat label="Cost" value="$0.003" mono />
      </div>

      <div className="sb-label" style={{ marginBottom: 12 }}>Timeline</div>
      <div style={{ background: "var(--sb-card)", border: "1px solid var(--sb-line)" }}>
        {steps.map((s, i) => <TimelineStep key={i} step={s} last={i === steps.length - 1} />)}
      </div>
    </div>
  );
}

function TimelineStep({ step, last }) {
  const col = { done: "var(--sb-accent)", active: "var(--sb-warm)", pending: "var(--sb-fg-5)", failed: "var(--sb-hot)" }[step.status];
  const kindLabel = { run: "step.run", sleep: "step.sleep", wait_for_event: "step.waitForEvent", branch: "branch" }[step.kind];
  return (
    <div style={{ display: "flex", gap: 14, padding: "14px 18px", borderBottom: last ? "none" : "1px solid var(--sb-line)", position: "relative" }}>
      <div style={{ width: 28, display: "flex", flexDirection: "column", alignItems: "center", position: "relative" }}>
        <div style={{
          width: 20, height: 20, border: `1.5px solid ${col}`,
          background: step.status === "done" ? col : "transparent",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: step.status === "active" ? `0 0 12px ${col}` : "none",
        }}>
          {step.status === "done" && <SBIcon name="check" size={11} stroke={2.5} />}
          {step.status === "active" && <div style={{ width: 6, height: 6, background: col, borderRadius: "50%", animation: "sb-pulse 1.5s infinite" }} />}
        </div>
        {!last && <div style={{ flex: 1, width: 1, background: step.status === "done" ? "var(--sb-accent-dim)" : "var(--sb-line-2)", marginTop: 4 }} />}
      </div>
      <div style={{ flex: 1, minWidth: 0, paddingBottom: last ? 0 : 4 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 12.5, fontWeight: 600, color: step.status === "pending" ? "var(--sb-fg-5)" : "var(--sb-fg)" }}>{step.name}</span>
          <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 10, color: "var(--sb-fg-5)", textTransform: "uppercase", letterSpacing: "0.12em" }}>{kindLabel}</span>
          <div style={{ flex: 1 }} />
          {step.ms && <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 10.5, color: "var(--sb-fg-5)" }}>{step.ms}ms</span>}
          {step.duration && <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 10.5, color: step.status === "active" ? "var(--sb-warm)" : "var(--sb-fg-5)" }}>{step.duration}</span>}
        </div>
        {(step.result || step.detail) && <div style={{ fontSize: 11.5, color: "var(--sb-fg-4)", marginTop: 3 }}>{step.result || step.detail}</div>}
      </div>
    </div>
  );
}

function ReportsView() {
  const bars = [42, 51, 48, 63, 58, 72, 68, 89];
  return (
    <div style={{ padding: "28px 32px", maxWidth: 1100 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <span className="sb-label" style={{ color: "var(--sb-accent)" }}>Week 16 · Apr 13 — Apr 19</span>
        <SBChip tone="violet" icon="jarvis">Generated by Jarvis · haiku-4.5</SBChip>
      </div>
      <h1 style={{ fontFamily: "var(--sb-font-display)", fontSize: 40, fontWeight: 600, letterSpacing: "-0.03em", margin: "0 0 24px", lineHeight: 1.05 }}>
        A quiet week. <span style={{ color: "var(--sb-accent)" }}>Three hot signals.</span>
      </h1>

      <div className="sb-brackets" style={{ padding: "26px 28px", background: "var(--sb-card)", marginBottom: 28, maxWidth: 860 }}>
        <p style={{ fontSize: 16, lineHeight: 1.65, color: "var(--sb-fg-2)", margin: 0 }}>
          Pipeline volume slipped <strong style={{ color: "var(--sb-fg)" }}>12%</strong> week-over-week but score quality improved — the median lead score climbed from 54 to 61. Three leads crossed into hot overnight, all from the Product Hunt scraper. Cold-outbound reply rate held steady at <strong style={{ color: "var(--sb-accent)" }}>8.4%</strong>; warm sequences doubled that. Rohan Shah (Lendly) moved to Qualified after a strong discovery call — biggest forecasted deal of the week at ₹22L.
        </p>
        <p style={{ fontSize: 14, lineHeight: 1.65, color: "var(--sb-fg-3)", margin: "14px 0 0" }}>
          Three things to watch next week: the HubSpot connector lagged twice (alerts raised), the LinkedIn scraper is getting throttled past 40 profiles/hr, and the warm_v1 template's day-5 breakup line is under-performing — consider A/B.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 28 }}>
        <SBStat label="New leads" value="34" delta="−12%" trend="down" mono />
        <SBStat label="Hot leads" value="12" delta="+3" trend="up" mono />
        <SBStat label="Reply rate" value="8.4%" delta="+0.2" trend="up" mono />
        <SBStat label="Forecast" value="₹1.8Cr" delta="+₹22L" trend="up" mono />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 16 }}>
        <SBCard style={{ padding: 22 }}>
          <div className="sb-label" style={{ marginBottom: 14 }}>Leads by week</div>
          <div style={{ display: "flex", alignItems: "stretch", gap: 8, height: 160 }}>
            {bars.map((h, i) => (
              <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                <div style={{ flex: 1, width: "100%", display: "flex", alignItems: "flex-end" }}>
                  <div style={{ width: "100%", background: i === bars.length - 1 ? "var(--sb-accent)" : "var(--sb-card-2)", height: `${h}%`, border: i === bars.length - 1 ? "none" : "1px solid var(--sb-line-2)", transition: "all 300ms" }} />
                </div>
                <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 9.5, color: "var(--sb-fg-5)" }}>W{9 + i}</span>
              </div>
            ))}
          </div>
        </SBCard>
        <SBCard style={{ padding: 22 }}>
          <div className="sb-label" style={{ marginBottom: 14 }}>Top sources</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {[
              { s: "HubSpot", v: 38, c: "var(--sb-accent)" },
              { s: "Product Hunt", v: 22, c: "var(--sb-violet)" },
              { s: "LinkedIn scraper", v: 18, c: "var(--sb-warm)" },
              { s: "Sheets import", v: 14, c: "var(--sb-cool)" },
              { s: "Jarvis", v: 8, c: "var(--sb-lime)" },
            ].map((r) => (
              <div key={r.s}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, marginBottom: 4, gap: 10 }}>
                  <span style={{ color: "var(--sb-fg-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.s}</span>
                  <span style={{ fontFamily: "var(--sb-font-mono)", color: "var(--sb-fg-4)", whiteSpace: "nowrap" }}>{r.v}</span>
                </div>
                <div style={{ height: 4, background: "var(--sb-panel)" }}>
                  <div style={{ height: "100%", width: `${r.v * 2.2}%`, background: r.c }} />
                </div>
              </div>
            ))}
          </div>
        </SBCard>
      </div>
    </div>
  );
}
window.ReportsView = ReportsView;
