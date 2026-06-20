// Jarvis drawer — the signature surface. Right-slide over dashboards.
// Has: message stream, tool-call cards, slash menu, voice input toggle, token counter.

const JARVIS_SEED = [
  { role: "user", text: "Anything hot this morning?" },
  { role: "jarvis", parts: [
    { kind: "text", text: "3 leads crossed into hot overnight. Two from Product Hunt scrape, one HubSpot import." },
    { kind: "tool", name: "get_leads", args: "{ since: '24h' }", result: "3 leads · scores 82, 79, 77" },
    { kind: "leads", items: [
      { name: "Priya Krishnan", co: "Rupee.co", score: 82, why: "Engaged twice on pricing page" },
      { name: "Arjun Mehta",   co: "Orbit Labs", score: 79, why: "Posted about switching from HubSpot" },
      { name: "Deepak Reddy",  co: "Stacklane", score: 77, why: "Downloaded the API gateway guide" },
    ]},
    { kind: "text", text: "Priya is the strongest — she's a repeat visitor and her team tried our sandbox last week. Want me to start the warm-outbound sequence for her?" },
  ]},
];

function JarvisDrawer({ open, onClose }) {
  const [messages, setMessages] = React.useState(JARVIS_SEED);
  const [input, setInput] = React.useState("");
  const [showSlash, setShowSlash] = React.useState(false);
  const [thinking, setThinking] = React.useState(false);
  const scrollRef = React.useRef(null);

  React.useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, thinking]);

  const send = (text) => {
    if (!text.trim()) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput(""); setShowSlash(false); setThinking(true);
    setTimeout(() => {
      setMessages((m) => [...m, {
        role: "jarvis", parts: [
          { kind: "tool", name: "automation__start_sequence", args: '{ lead: "priya@rupee.co", template: "warm_v1" }', result: "Sequence queued · first send in 45 min" },
          { kind: "text", text: "Done. She'll get day-0 in 45 minutes. I'll branch on open/reply — you'll see it in the Automation timeline." },
        ]
      }]);
      setThinking(false);
    }, 1200);
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
    if (e.key === "/" && input === "") { setShowSlash(true); }
    if (e.key === "Escape") { setShowSlash(false); }
  };

  if (!open) return null;

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 40, backdropFilter: "blur(2px)" }} />
      <aside style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: 520,
        background: "var(--sb-bg)", borderLeft: "1px solid var(--sb-line-2)",
        display: "flex", flexDirection: "column", zIndex: 50,
        boxShadow: "-40px 0 80px rgba(0,0,0,0.6)",
        animation: "sb-slide-in 280ms cubic-bezier(.2,.8,.2,1) forwards",
      }}>
        {/* Header */}
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--sb-line)", display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ position: "relative", width: 32, height: 32, background: "var(--sb-accent-bg)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--sb-accent)" }}>
            <SBIcon name="jarvis" size={18} stroke={1.3} />
            <div style={{ position: "absolute", inset: -2, border: "1px solid var(--sb-accent)", opacity: 0.3, animation: "sb-ping 2s infinite" }} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: "var(--sb-font-display)" }}>Jarvis</div>
            <div style={{ fontSize: 10.5, fontFamily: "var(--sb-font-mono)", color: "var(--sb-fg-5)", letterSpacing: "0.1em" }}>
              haiku-4.5 · 8 tools connected
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 8px", background: "var(--sb-panel)", fontSize: 10.5, fontFamily: "var(--sb-font-mono)", color: "var(--sb-fg-4)" }}>
            <span style={{ color: "var(--sb-accent)" }}>432</span>/2000 tok
          </div>
          <button onClick={onClose} style={{ background: "transparent", border: "none", color: "var(--sb-fg-4)", cursor: "pointer", padding: 4 }}>
            <SBIcon name="close" size={16} />
          </button>
        </div>

        {/* Message stream */}
        <div ref={scrollRef} style={{ flex: 1, overflow: "auto", padding: "20px 20px 12px" }}>
          {messages.map((m, i) => <JarvisMessage key={i} m={m} />)}
          {thinking && <JarvisThinking />}
        </div>

        {/* Composer */}
        <div style={{ padding: "12px 16px 16px", borderTop: "1px solid var(--sb-line)", position: "relative" }}>
          {showSlash && <SlashMenu onPick={(cmd) => { setInput(cmd); setShowSlash(false); }} />}

          <div style={{ display: "flex", alignItems: "flex-end", gap: 8, background: "var(--sb-panel)", border: "1px solid var(--sb-line-2)", padding: "8px 10px" }}>
            <button onClick={() => setShowSlash((v) => !v)} style={{ background: "transparent", border: "none", color: showSlash ? "var(--sb-accent)" : "var(--sb-fg-4)", cursor: "pointer", padding: 4, marginBottom: 2 }}>
              <SBIcon name="slash" size={14} />
            </button>
            <textarea
              value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown}
              placeholder="Ask Jarvis. Type / for commands."
              rows={1}
              style={{
                flex: 1, background: "transparent", border: "none", outline: "none",
                color: "var(--sb-fg)", fontFamily: "var(--sb-font)", fontSize: 13,
                resize: "none", padding: "4px 0", maxHeight: 120, lineHeight: 1.5,
              }}
            />
            <button style={{ background: "transparent", border: "none", color: "var(--sb-fg-4)", cursor: "pointer", padding: 4, marginBottom: 2 }}>
              <SBIcon name="mic" size={14} />
            </button>
            <button onClick={() => send(input)} disabled={!input.trim()} style={{
              background: input.trim() ? "var(--sb-accent)" : "var(--sb-card)",
              color: input.trim() ? "#000" : "var(--sb-fg-5)", border: "none",
              padding: "7px 10px", cursor: input.trim() ? "pointer" : "not-allowed",
              display: "flex", alignItems: "center",
            }}>
              <SBIcon name="send" size={13} />
            </button>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 10.5, fontFamily: "var(--sb-font-mono)", color: "var(--sb-fg-5)" }}>
            <span><SBKbd>/</SBKbd> commands · <SBKbd>@</SBKbd> mention · <SBKbd>⏎</SBKbd> send</span>
            <span>SSE · data-stream v1</span>
          </div>
        </div>
      </aside>
    </>
  );
}
window.JarvisDrawer = JarvisDrawer;

function JarvisMessage({ m }) {
  if (m.role === "user") {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 18 }}>
        <div style={{
          maxWidth: "80%", background: "var(--sb-card)", border: "1px solid var(--sb-line-2)",
          padding: "10px 14px", fontSize: 13, lineHeight: 1.55, color: "var(--sb-fg)",
        }}>{m.text}</div>
      </div>
    );
  }
  return (
    <div style={{ marginBottom: 22, display: "flex", gap: 10 }}>
      <div style={{ width: 24, height: 24, background: "var(--sb-accent-bg)", color: "var(--sb-accent)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 2 }}>
        <SBIcon name="jarvis" size={13} stroke={1.5} />
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
        {m.parts.map((p, i) => <MessagePart key={i} p={p} />)}
      </div>
    </div>
  );
}

function MessagePart({ p }) {
  if (p.kind === "text") {
    return <div style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--sb-fg-2)" }}>{p.text}</div>;
  }
  if (p.kind === "tool") {
    return (
      <div style={{ fontFamily: "var(--sb-font-mono)", fontSize: 11, border: "1px solid var(--sb-line)", background: "var(--sb-bg-2)" }}>
        <div style={{ padding: "6px 10px", borderBottom: "1px solid var(--sb-line)", display: "flex", alignItems: "center", gap: 6, color: "var(--sb-violet)" }}>
          <SBIcon name="tool" size={11} stroke={1.6} />
          <span style={{ fontWeight: 700 }}>{p.name}</span>
          <span style={{ color: "var(--sb-fg-5)", marginLeft: "auto" }}>{p.args}</span>
        </div>
        <div style={{ padding: "6px 10px", color: "var(--sb-accent)", display: "flex", alignItems: "center", gap: 6 }}>
          <SBIcon name="check" size={10} stroke={2} /> {p.result}
        </div>
      </div>
    );
  }
  if (p.kind === "leads") {
    return (
      <div style={{ border: "1px solid var(--sb-line)", background: "var(--sb-card)" }}>
        {p.items.map((l, i) => (
          <div key={i} style={{
            padding: "10px 12px",
            borderTop: i > 0 ? "1px solid var(--sb-line)" : "none",
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <SBAvatar name={l.name} color="var(--sb-violet)" size={28} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--sb-fg)", display: "flex", alignItems: "center", gap: 6 }}>
                {l.name}
                <span style={{ color: "var(--sb-fg-5)", fontWeight: 400 }}>· {l.co}</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--sb-fg-4)", marginTop: 2 }}>{l.why}</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
              <div style={{ fontFamily: "var(--sb-font-mono)", fontSize: 14, fontWeight: 700, color: l.score > 80 ? "var(--sb-hot)" : "var(--sb-warm)" }}>{l.score}</div>
              <div style={{ fontSize: 9, color: "var(--sb-fg-5)", textTransform: "uppercase", letterSpacing: "0.15em", fontFamily: "var(--sb-font-mono)" }}>hot</div>
            </div>
          </div>
        ))}
      </div>
    );
  }
  return null;
}

function JarvisThinking() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--sb-fg-4)", fontSize: 12, fontFamily: "var(--sb-font-mono)", marginBottom: 18 }}>
      <div style={{ width: 24, height: 24, background: "var(--sb-accent-bg)", color: "var(--sb-accent)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <SBIcon name="jarvis" size={13} stroke={1.5} />
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{ width: 5, height: 5, background: "var(--sb-accent)", borderRadius: "50%", animation: `sb-bounce 1.4s infinite ${i * 0.15}s` }} />
        ))}
      </div>
      <span>calling tools…</span>
    </div>
  );
}

const SLASH_CMDS = [
  { cmd: "/leads", desc: "list, filter, or explain leads", color: "var(--sb-violet)" },
  { cmd: "/score", desc: "re-run the scoring rubric on a lead", color: "var(--sb-warm)" },
  { cmd: "/send", desc: "trigger an outbound sequence", color: "var(--sb-accent)" },
  { cmd: "/report", desc: "generate a custom period report", color: "var(--sb-cool)" },
  { cmd: "/doc", desc: "search the doc store (RAG)", color: "var(--sb-lime)" },
  { cmd: "/memory", desc: "recall long-term facts", color: "var(--sb-fg-3)" },
];

function SlashMenu({ onPick }) {
  return (
    <div style={{
      position: "absolute", bottom: "100%", left: 16, right: 16, marginBottom: 8,
      background: "var(--sb-card-2)", border: "1px solid var(--sb-line-3)",
      padding: 6, zIndex: 5, boxShadow: "0 -8px 32px rgba(0,0,0,0.6)",
    }}>
      <div style={{ padding: "4px 8px 8px", borderBottom: "1px solid var(--sb-line)", marginBottom: 6 }}>
        <div className="sb-label">slash commands</div>
      </div>
      {SLASH_CMDS.map((c) => (
        <button key={c.cmd} onClick={() => onPick(c.cmd + " ")} style={{
          display: "flex", alignItems: "center", gap: 10, width: "100%",
          padding: "6px 8px", background: "transparent", border: "none",
          cursor: "pointer", textAlign: "left", fontFamily: "inherit",
        }}
          onMouseEnter={(e) => e.currentTarget.style.background = "var(--sb-panel)"}
          onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
        >
          <span style={{ fontFamily: "var(--sb-font-mono)", fontSize: 12, fontWeight: 700, color: c.color, minWidth: 70 }}>{c.cmd}</span>
          <span style={{ fontSize: 12, color: "var(--sb-fg-3)" }}>{c.desc}</span>
        </button>
      ))}
    </div>
  );
}
