// M2 Leads — Kanban + lead drawer with score explainer.

const STAGES = ["New", "Contacted", "Qualified", "Meeting", "Proposal"];
const LEADS = [
  { id: 1, stage: "New", name: "Priya Krishnan", co: "Rupee.co", score: 82, tags: ["hot"], source: "producthunt", owner: "RS", value: "₹8L" },
  { id: 2, stage: "New", name: "Arjun Mehta", co: "Orbit Labs", score: 79, tags: ["hot"], source: "linkedin", owner: "AK", value: "₹12L" },
  { id: 3, stage: "New", name: "Nisha Varma", co: "Flux", score: 54, tags: ["warm"], source: "hubspot", owner: "RS", value: "₹4L" },
  { id: 4, stage: "Contacted", name: "Deepak Reddy", co: "Stacklane", score: 77, tags: ["hot"], source: "scraper", owner: "AK", value: "₹15L" },
  { id: 5, stage: "Contacted", name: "Kavya Iyer", co: "Paisa Labs", score: 61, tags: ["warm"], source: "sheets", owner: "RS", value: "₹6L" },
  { id: 6, stage: "Qualified", name: "Rohan Shah", co: "Lendly", score: 88, tags: ["hot", "fintech"], source: "jarvis", owner: "RS", value: "₹22L" },
  { id: 7, stage: "Qualified", name: "Sana Ahmad", co: "Nudge AI", score: 71, tags: ["warm"], source: "hubspot", owner: "AK", value: "₹9L" },
  { id: 8, stage: "Meeting", name: "Vikram Anand", co: "Payroll.io", score: 84, tags: ["hot", "fintech"], source: "hubspot", owner: "RS", value: "₹28L" },
  { id: 9, stage: "Proposal", name: "Meera Singh", co: "Terra Logistics", score: 91, tags: ["hot"], source: "linkedin", owner: "AK", value: "₹45L" },
];

function LeadsView({ onOpenJarvis }) {
  const [selected, setSelected] = React.useState(null);
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 60px)" }}>
      <div style={{ padding: "16px 28px", borderBottom: "1px solid var(--sb-line)", display: "flex", alignItems: "center", gap: 12 }}>
        <SBChip tone="accent" icon="dot">156 leads</SBChip>
        <SBChip tone="hot">12 hot</SBChip>
        <SBChip tone="warm">34 warm</SBChip>
        <div style={{ flex: 1 }} />
        <SBButton variant="ghost" size="sm" icon="filter">Filters · 2</SBButton>
        <SBButton variant="secondary" size="sm" icon="spark" onClick={onOpenJarvis}>Ask Jarvis</SBButton>
        <SBButton variant="primary" size="sm" icon="plus">Add lead</SBButton>
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${STAGES.length}, minmax(260px, 1fr))`, gap: 14, minWidth: 1200 }}>
          {STAGES.map((s) => {
            const col = LEADS.filter((l) => l.stage === s);
            return (
              <div key={s} style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 4px 10px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="sb-label">{s}</span>
                    <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 11, color: "var(--sb-fg-4)" }}>{col.length}</span>
                  </div>
                  <button style={{ background: "transparent", border: "none", color: "var(--sb-fg-5)", cursor: "pointer", padding: 2 }}><SBIcon name="plus" size={12} /></button>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {col.map((l) => <LeadCard key={l.id} lead={l} onClick={() => setSelected(l)} />)}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {selected && <LeadDrawer lead={selected} onClose={() => setSelected(null)} onOpenJarvis={onOpenJarvis} />}
    </div>
  );
}
window.LeadsView = LeadsView;

function LeadCard({ lead, onClick }) {
  const [hover, setHover] = React.useState(false);
  const scoreTone = lead.score >= 80 ? "var(--sb-hot)" : lead.score >= 60 ? "var(--sb-warm)" : "var(--sb-fg-4)";
  return (
    <div onClick={onClick} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} style={{
      padding: 12, background: "var(--sb-card)", border: `1px solid ${hover ? "var(--sb-line-3)" : "var(--sb-line)"}`,
      cursor: "pointer", transition: "border-color 160ms",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, marginBottom: 8 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--sb-fg)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{lead.name}</div>
          <div style={{ fontSize: 11.5, color: "var(--sb-fg-4)", marginTop: 2 }}>{lead.co}</div>
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 2, fontFamily: "var(--sb-font-mono)", color: scoreTone }}>
          <span style={{ fontSize: 18, fontWeight: 700, lineHeight: 1 }}>{lead.score}</span>
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
        <div style={{ display: "flex", gap: 4 }}>{lead.tags.map((t) => <SBChip key={t} tone={t === "hot" ? "hot" : t === "fintech" ? "cool" : "warm"}>{t}</SBChip>)}</div>
        <div style={{ fontFamily: "var(--sb-font-mono)", fontSize: 11, color: "var(--sb-fg-3)" }}>{lead.value}</div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--sb-line)", fontSize: 10.5, color: "var(--sb-fg-5)", fontFamily: "var(--sb-font-mono)" }}>
        <SBIcon name={lead.source === "linkedin" ? "linkedin" : lead.source === "jarvis" ? "jarvis" : "building"} size={11} stroke={1.4} />
        {lead.source}
        <span style={{ marginLeft: "auto" }}>{lead.owner}</span>
      </div>
    </div>
  );
}

function LeadDrawer({ lead, onClose, onOpenJarvis }) {
  const reasons = [
    { r: "Visited pricing page 3× in last 7 days", w: +22 },
    { r: "Company raised Series A in Feb 2026", w: +18 },
    { r: "Role: Head of Engineering · high seniority", w: +15 },
    { r: "Industry (fintech) matches ICP", w: +12 },
    { r: "Replied to day-0 outbound email in < 2 hours", w: +15 },
    { r: "No website tech overlap with current stack", w: -6 },
  ];
  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 30 }} />
      <aside style={{ position: "fixed", top: 0, right: 0, bottom: 0, width: 540, background: "var(--sb-bg)", borderLeft: "1px solid var(--sb-line-2)", overflow: "auto", zIndex: 35, animation: "sb-slide-in 240ms cubic-bezier(.2,.8,.2,1) forwards" }}>
        <div style={{ padding: "18px 24px", borderBottom: "1px solid var(--sb-line)", display: "flex", alignItems: "center", gap: 12 }}>
          <SBAvatar name={lead.name} color="var(--sb-violet)" size={40} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{lead.name}</div>
            <div style={{ fontSize: 12, color: "var(--sb-fg-4)", fontFamily: "var(--sb-font-mono)" }}>{lead.co} · {lead.value}</div>
          </div>
          <button onClick={onClose} style={{ background: "transparent", border: "none", color: "var(--sb-fg-4)", cursor: "pointer" }}><SBIcon name="close" size={16} /></button>
        </div>

        <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 24 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <span className="sb-label">Score · explained</span>
              <SBChip tone="hot" icon="flame">hot</SBChip>
            </div>
            <div className="sb-brackets" style={{ padding: "18px 20px", background: "var(--sb-card)" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 14 }}>
                <div style={{ fontSize: 44, fontWeight: 500, letterSpacing: "-0.03em", fontFamily: "var(--sb-font-mono)", color: "var(--sb-hot)", lineHeight: 1 }}>{lead.score}</div>
                <div style={{ fontSize: 12, color: "var(--sb-fg-4)", fontFamily: "var(--sb-font-mono)" }}>/100 · rubric v3 · haiku-4.5</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {reasons.map((r, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12.5 }}>
                    <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 11, fontWeight: 700, color: r.w > 0 ? "var(--sb-accent)" : "var(--sb-hot)", minWidth: 34 }}>{r.w > 0 ? "+" : ""}{r.w}</span>
                    <span style={{ color: "var(--sb-fg-2)", flex: 1 }}>{r.r}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div>
            <div className="sb-label" style={{ marginBottom: 10 }}>Timeline</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {[
                { t: "02:14", what: "Email opened", detail: "day-0 outbound · warm_v1", icon: "mail", color: "var(--sb-accent)" },
                { t: "yesterday", what: "Sequence started", detail: "Jarvis triggered warm_v1", icon: "flow", color: "var(--sb-violet)" },
                { t: "2d ago", what: "Enriched", detail: "Apollo + website analysis · +22 pts", icon: "spark", color: "var(--sb-warm)" },
                { t: "3d ago", what: "Scraped", detail: "Product Hunt · launched \"Rupee Invoicing\"", icon: "leads", color: "var(--sb-fg-4)" },
              ].map((e, i) => (
                <div key={i} style={{ display: "flex", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--sb-line)" }}>
                  <div style={{ width: 24, height: 24, background: "var(--sb-card)", border: "1px solid var(--sb-line-2)", display: "flex", alignItems: "center", justifyContent: "center", color: e.color, flexShrink: 0 }}>
                    <SBIcon name={e.icon} size={11} stroke={1.5} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12.5, color: "var(--sb-fg)", fontWeight: 600 }}>{e.what}</div>
                    <div style={{ fontSize: 11.5, color: "var(--sb-fg-4)", marginTop: 2 }}>{e.detail}</div>
                  </div>
                  <div style={{ fontSize: 10.5, color: "var(--sb-fg-5)", fontFamily: "var(--sb-font-mono)" }}>{e.t}</div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <SBButton variant="primary" icon="bolt">Start sequence</SBButton>
            <SBButton variant="secondary" icon="mail">Email</SBButton>
            <SBButton variant="ghost" icon="jarvis" onClick={onOpenJarvis}>Ask Jarvis</SBButton>
          </div>
        </div>
      </aside>
    </>
  );
}
