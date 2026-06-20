import React from 'react';

const SLASH_CMDS = [
  { cmd: '/leads',  desc: 'list, filter, or explain leads',          color: 'var(--sb-violet)' },
  { cmd: '/score',  desc: 're-run the scoring rubric on a lead',     color: 'var(--sb-warm)' },
  { cmd: '/send',   desc: 'trigger an outbound sequence',            color: 'var(--sb-accent)' },
  { cmd: '/report', desc: 'generate a custom period report',         color: 'var(--sb-cool)' },
  { cmd: '/doc',    desc: 'search the doc store (RAG)',              color: 'var(--sb-lime)' },
  { cmd: '/memory', desc: 'recall long-term facts',                  color: 'var(--sb-fg-3)' },
];

// Floating menu that sits above the composer when the user hits `/`. Clicks
// insert the command into the input (caller decides — we just emit onPick).
export default function SlashMenu({ onPick }) {
  return (
    <div style={{
      position: 'absolute', bottom: '100%', left: 16, right: 16, marginBottom: 8,
      background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-3)',
      padding: 6, zIndex: 5, boxShadow: '0 -8px 32px rgba(0,0,0,0.6)',
    }}>
      <div style={{
        padding: '4px 8px 8px', borderBottom: '1px solid var(--sb-line)',
        marginBottom: 6,
      }}>
        <div className="sb-label">slash commands</div>
      </div>
      {SLASH_CMDS.map((c) => (
        <button
          key={c.cmd}
          onClick={() => onPick(c.cmd + ' ')}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--sb-panel)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
          style={{
            display: 'flex', alignItems: 'center', gap: 10, width: '100%',
            padding: '6px 8px', background: 'transparent', border: 'none',
            cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
          }}
        >
          <span style={{
            fontFamily: 'var(--sb-font-mono)', fontSize: 12, fontWeight: 700,
            color: c.color, minWidth: 70,
          }}>{c.cmd}</span>
          <span style={{ fontSize: 12, color: 'var(--sb-fg-3)' }}>{c.desc}</span>
        </button>
      ))}
    </div>
  );
}
