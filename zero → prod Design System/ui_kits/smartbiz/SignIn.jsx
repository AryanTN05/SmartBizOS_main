// Auth / demo-mode splash.

function SignIn({ onDemo, onSignIn }) {
  return (
    <div style={{ minHeight: "100vh", display: "grid", gridTemplateColumns: "1fr 1fr", background: "var(--sb-bg)" }}>
      <div style={{ padding: "48px 56px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: "100vh" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 32, height: 32, background: "var(--sb-accent)", color: "#000", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--sb-font-display)", fontSize: 18, fontWeight: 700, letterSpacing: "-0.04em" }}>sb</div>
          <div>
            <div style={{ fontFamily: "var(--sb-font-display)", fontSize: 16, fontWeight: 600, letterSpacing: "-0.01em" }}>SmartBiz OS</div>
            <div style={{ fontSize: 10.5, color: "var(--sb-fg-5)", fontFamily: "var(--sb-font-mono)", letterSpacing: "0.1em" }}>by zero → prod</div>
          </div>
        </div>

        <div style={{ maxWidth: 420 }}>
          <div className="sb-label" style={{ color: "var(--sb-accent)", marginBottom: 14, display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ width: 24, height: 1, background: "var(--sb-accent)" }} /> The AI business OS
          </div>
          <h1 style={{ fontFamily: "var(--sb-font-display)", fontSize: 52, fontWeight: 500, letterSpacing: "-0.035em", lineHeight: 1.02, margin: "0 0 18px" }}>
            Every module.<br/>
            One brain.<br/>
            <span style={{ color: "var(--sb-accent)" }}>Jarvis.</span>
          </h1>
          <p style={{ fontSize: 15, color: "var(--sb-fg-3)", margin: "0 0 32px", lineHeight: 1.55 }}>
            Leads, sequences, reports, docs — all wired to one conversational layer. Ask Jarvis anything. It reads. It writes. It acts.
          </p>

          <SBButton variant="primary" size="lg" icon="bolt" onClick={onDemo}>Try the 5-min demo</SBButton>
          <SBButton variant="ghost" size="lg" onClick={onSignIn}>Sign in</SBButton>

          <div style={{ marginTop: 32, display: "flex", flexDirection: "column", gap: 8, fontSize: 11.5, color: "var(--sb-fg-5)", fontFamily: "var(--sb-font-mono)" }}>
            <div>▸ anonymous · no email · 2000 tokens · 1 session / IP / hour</div>
            <div>▸ seed data only · nothing you do will send real emails</div>
          </div>
        </div>

        <div style={{ fontSize: 10.5, color: "var(--sb-fg-5)", fontFamily: "var(--sb-font-mono)", letterSpacing: "0.12em" }}>
          V0 · ZERO → PROD · MCP-first
        </div>
      </div>

      <div style={{ borderLeft: "1px solid var(--sb-line)", background: "var(--sb-bg-2)", position: "relative", overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center", padding: 40 }}>
        <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(#888 1px, transparent 1px), linear-gradient(90deg, #888 1px, transparent 1px)", backgroundSize: "48px 48px", opacity: 0.04, maskImage: "radial-gradient(ellipse 60% 60% at 50% 50%, black 20%, transparent 100%)" }} />
        <div style={{ position: "relative", width: "100%", maxWidth: 460, display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="sb-brackets" style={{ padding: 18, background: "var(--sb-card)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, fontFamily: "var(--sb-font-mono)", fontSize: 11 }}>
              <span style={{ color: "var(--sb-fg-5)" }}>▸</span>
              <span style={{ color: "var(--sb-fg-3)" }}>"anything hot this morning?"</span>
            </div>
            <div style={{ padding: 12, background: "var(--sb-bg-2)", border: "1px solid var(--sb-line)", fontFamily: "var(--sb-font-mono)", fontSize: 11, marginBottom: 10 }}>
              <div style={{ color: "var(--sb-violet)" }}>▸ get_leads <span style={{ color: "var(--sb-fg-5)" }}>{"{ since: '24h' }"}</span></div>
              <div style={{ color: "var(--sb-accent)", marginTop: 4 }}>✓ 3 leads · scores 82, 79, 77</div>
            </div>
            <div style={{ fontSize: 12.5, color: "var(--sb-fg-2)", lineHeight: 1.55 }}>
              3 leads crossed into hot overnight. Priya is the strongest — repeat pricing visitor, tried the sandbox. Want me to start a warm outbound?
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {["M1 Jarvis", "M2 Sales Intel", "M3 Automation", "M6 Reports", "Docs + RAG"].map((x) => (
              <SBChip key={x} tone="muted">{x}</SBChip>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
window.SignIn = SignIn;

function Home({ onOpenJarvis }) {
  return (
    <div style={{ padding: "28px 32px" }}>
      <div style={{ marginBottom: 28 }}>
        <div className="sb-label" style={{ color: "var(--sb-accent)", marginBottom: 8 }}>Morning, Ravi</div>
        <h1 style={{ fontFamily: "var(--sb-font-display)", fontSize: 36, fontWeight: 600, margin: 0, letterSpacing: "-0.025em" }}>
          3 hot. 2 failed runs. <span style={{ color: "var(--sb-fg-5)" }}>1 report waiting.</span>
        </h1>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 28 }}>
        <SBStat label="Active leads" value="156" delta="+12" trend="up" mono />
        <SBStat label="Hot" value="12" delta="+3" trend="up" mono />
        <SBStat label="Runs · 24h" value="47" delta="2 failed" trend="hot" mono />
        <SBStat label="Reply rate" value="8.4%" delta="+0.2" trend="up" mono />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 16 }}>
        <SBCard style={{ padding: 24 }} bracket>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
            <div style={{ width: 28, height: 28, background: "var(--sb-accent-bg)", color: "var(--sb-accent)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <SBIcon name="jarvis" size={14} stroke={1.4} />
            </div>
            <span className="sb-label">Jarvis · suggested</span>
          </div>
          <p style={{ fontSize: 17, lineHeight: 1.5, color: "var(--sb-fg)", margin: "0 0 18px", fontFamily: "var(--sb-font-display)", fontWeight: 500, letterSpacing: "-0.01em" }}>
            "Priya Krishnan just opened your day-0 email. She's at <span style={{ color: "var(--sb-accent)" }}>82</span>. Want me to queue a follow-up and loop in sales?"
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <SBButton variant="primary" icon="bolt" onClick={onOpenJarvis}>Yes, do it</SBButton>
            <SBButton variant="ghost" onClick={onOpenJarvis}>Ask more</SBButton>
          </div>
        </SBCard>

        <SBCard style={{ padding: 24 }}>
          <div className="sb-label" style={{ marginBottom: 14 }}>Last week · in one sentence</div>
          <p style={{ fontSize: 15, lineHeight: 1.55, color: "var(--sb-fg-2)", margin: "0 0 12px" }}>
            Volume slipped 12% but quality climbed — median score 54→61, and Rohan (Lendly, ₹22L) moved to Qualified.
          </p>
          <SBButton variant="ghost" size="sm" iconRight="arrow">Full report</SBButton>
        </SBCard>
      </div>
    </div>
  );
}
window.Home = Home;
