// SmartBiz OS — app chrome: left nav + top bar
// Jarvis is a right-drawer, not in the sidebar.

const MODULES = [
  { key: "jarvis",   label: "Jarvis",    icon: "jarvis",   hint: "Ask anything" },
  { key: "leads",    label: "Leads",     icon: "leads",    hint: "M2 Sales Intel" },
  { key: "flow",     label: "Automation",icon: "flow",     hint: "M3 Workflows" },
  { key: "reports",  label: "Reports",   icon: "reports",  hint: "M6" },
  { key: "docs",     label: "Docs",      icon: "docs",     hint: "RAG store" },
];

function SBSidebar({ active, onNav, onJarvis, demo }) {
  return (
    <aside style={{
      width: 72, borderRight: "1px solid var(--sb-line)",
      background: "var(--sb-bg-2)", display: "flex", flexDirection: "column",
      alignItems: "center", padding: "16px 0 14px", position: "sticky", top: 0, height: "100vh",
    }}>
      {/* Logo */}
      <div style={{
        width: 40, height: 40, background: "var(--sb-accent)", color: "#000",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "var(--sb-font-display)", fontSize: 22, fontWeight: 700,
        letterSpacing: "-0.04em", marginBottom: 24,
      }}>sb</div>

      <nav style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4, width: "100%", alignItems: "center" }}>
        {MODULES.map((m) => {
          const isJarvis = m.key === "jarvis";
          const isActive = active === m.key;
          return (
            <NavBtn
              key={m.key}
              item={m}
              active={isActive}
              onClick={isJarvis ? onJarvis : () => onNav(m.key)}
            />
          );
        })}
      </nav>

      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, paddingTop: 12, width: "100%", borderTop: "1px solid var(--sb-line)" }}>
        {demo && (
          <div style={{
            writingMode: "vertical-rl", transform: "rotate(180deg)",
            fontSize: 9, letterSpacing: "0.24em", textTransform: "uppercase",
            color: "var(--sb-accent)", fontFamily: "var(--sb-font-mono)", fontWeight: 600,
            padding: "4px 0",
          }}>DEMO</div>
        )}
        <SBAvatar name="Ravi Shankar" color="var(--sb-accent)" size={32} />
      </div>
    </aside>
  );
}
window.SBSidebar = SBSidebar;

function NavBtn({ item, active, onClick }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div style={{ position: "relative", width: "100%", display: "flex", justifyContent: "center" }}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button onClick={onClick} style={{
        width: 44, height: 44, background: active ? "var(--sb-accent-bg)" : (hover ? "var(--sb-card)" : "transparent"),
        color: active ? "var(--sb-accent)" : hover ? "var(--sb-fg)" : "var(--sb-fg-3)",
        border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
        position: "relative", transition: "all 140ms",
      }}>
        <SBIcon name={item.icon} size={18} stroke={1.4} />
        {active && <div style={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 2, background: "var(--sb-accent)" }} />}
      </button>
      {hover && (
        <div style={{
          position: "absolute", left: 56, top: "50%", transform: "translateY(-50%)",
          background: "var(--sb-card-2)", border: "1px solid var(--sb-line-2)",
          padding: "6px 10px", fontSize: 11.5, whiteSpace: "nowrap", zIndex: 100,
          pointerEvents: "none", display: "flex", flexDirection: "column", gap: 2,
        }}>
          <div style={{ color: "var(--sb-fg)", fontWeight: 600 }}>{item.label}</div>
          <div style={{ color: "var(--sb-fg-5)", fontFamily: "var(--sb-font-mono)", fontSize: 10 }}>{item.hint}</div>
        </div>
      )}
    </div>
  );
}

function SBTopBar({ title, crumb, children, demo }) {
  return (
    <header style={{
      padding: "14px 28px", borderBottom: "1px solid var(--sb-line)",
      background: "var(--sb-bg)", position: "sticky", top: 0, zIndex: 10,
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 20,
    }}>
      <div style={{ minWidth: 0, flex: 1, display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ fontSize: 11, fontFamily: "var(--sb-font-mono)", color: "var(--sb-fg-5)", letterSpacing: "0.12em", textTransform: "uppercase", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>
          {crumb.map((c, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span style={{ color: "var(--sb-fg-6)", margin: "0 6px" }}>/</span>}
              <span style={{ color: i === crumb.length - 1 ? "var(--sb-fg-3)" : "var(--sb-fg-5)" }}>{c}</span>
            </React.Fragment>
          ))}
        </div>
        <h1 style={{ margin: 0, fontSize: 16, fontWeight: 600, fontFamily: "var(--sb-font-display)", letterSpacing: "-0.01em" }}>{title}</h1>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {children}
        {demo && <DemoCountdown />}
      </div>
    </header>
  );
}
window.SBTopBar = SBTopBar;

function DemoCountdown() {
  const [s, setS] = React.useState(4 * 60 + 37);
  React.useEffect(() => {
    const t = setInterval(() => setS((v) => (v > 0 ? v - 1 : 0)), 1000);
    return () => clearInterval(t);
  }, []);
  const m = Math.floor(s / 60); const sec = String(s % 60).padStart(2, "0");
  const low = s < 60;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, padding: "5px 10px",
      border: `1px solid ${low ? "var(--sb-hot)" : "var(--sb-line-2)"}`,
      fontFamily: "var(--sb-font-mono)", fontSize: 11, fontWeight: 600,
      color: low ? "var(--sb-hot)" : "var(--sb-accent)", whiteSpace: "nowrap", flexShrink: 0,
    }}>
      <div style={{ width: 6, height: 6, borderRadius: "50%", background: low ? "var(--sb-hot)" : "var(--sb-accent)",
        boxShadow: `0 0 8px ${low ? "var(--sb-hot)" : "var(--sb-accent)"}`, animation: "sb-pulse 1.5s infinite", flexShrink: 0 }} />
      DEMO · {m}:{sec}
    </div>
  );
}
window.DemoCountdown = DemoCountdown;
