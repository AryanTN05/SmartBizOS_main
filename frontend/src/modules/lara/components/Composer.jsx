import React, { useState } from 'react';
import { SBIcon, SBKbd } from '../../../components/primitives';
import SlashMenu from './SlashMenu.jsx';

// Composer — textarea + mic + send button + slash menu + hints row.
// `onSend(text)` fires on Enter / send-click. `voice` is the useVoiceSession
// state passed in by the parent (the drawer owns the voice session so it can
// also append transcripts to the message list without going through onSend).
export default function Composer({ onSend, disabled, voice }) {
  const [input, setInput] = useState('');
  const [showSlash, setShowSlash] = useState(false);
  // Defensive default so the component still renders if the parent forgets
  // to pass a voice prop (e.g. a future caller from outside the drawer).
  const v = voice || { state: 'idle', activity: 'quiet', error: null, volume: 0, start: () => {}, stop: () => {} };
  const normalizedVol = Math.min(1, (v.volume || 0) / 3000);

  const submit = () => {
    const t = input.trim();
    if (!t || disabled) return;
    onSend(t);
    setInput('');
    setShowSlash(false);
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); return; }
    if (e.key === '/' && input === '') { setShowSlash(true); return; }
    if (e.key === 'Escape') { setShowSlash(false); return; }
  };

  const canSend = !!input.trim() && !disabled;

  return (
    <div style={{
      padding: '12px 16px 16px', borderTop: '1px solid var(--sb-line)',
      position: 'relative', flexShrink: 0,
    }}>
      {showSlash && (
        <SlashMenu onPick={(cmd) => { setInput(cmd); setShowSlash(false); }} />
      )}

      <div style={{
        display: 'flex', alignItems: 'flex-end', gap: 8,
        background: 'var(--sb-panel)', border: '1px solid var(--sb-line-2)',
        padding: '8px 10px',
      }}>
        <button
          onClick={() => setShowSlash((v) => !v)}
          aria-label="Slash commands"
          style={{
            background: 'transparent', border: 'none',
            color: showSlash ? 'var(--sb-accent)' : 'var(--sb-fg-4)',
            cursor: 'pointer', padding: 4, marginBottom: 2,
          }}
        >
          <SBIcon name="slash" size={14} />
        </button>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask Lara. Type / for commands."
          rows={1}
          disabled={disabled}
          style={{
            flex: 1, background: 'transparent', border: 'none', outline: 'none',
            color: 'var(--sb-fg)', fontFamily: 'var(--sb-font)', fontSize: 13,
            resize: 'none', padding: '4px 0', maxHeight: 120, lineHeight: 1.5,
          }}
        />
        <button
          aria-label={v.state === 'listening' ? 'Stop voice' : 'Start voice'}
          onClick={() => (v.state === 'idle' || v.state === 'error' ? v.start() : v.stop())}
          title={v.error?.message || (v.state === 'listening' ? 'Listening — click to stop' : 'Voice input')}
          style={{
            position: 'relative',
            background: v.state === 'listening' ? 'rgba(255,90,106,0.15)' : 'transparent',
            border: 'none',
            color: v.state === 'listening' ? 'var(--sb-hot)'
                 : v.state === 'connecting' ? 'var(--sb-warm)'
                 : v.state === 'error' ? 'var(--sb-hot)'
                 : 'var(--sb-fg-4)',
            cursor: 'pointer', padding: 4, marginBottom: 2,
            animation: v.state === 'connecting' ? 'sb-pulse 1.6s ease-in-out infinite' : 'none',
          }}
        >
          {v.state === 'listening' && normalizedVol > 0.01 && (
            <span style={{
              position: 'absolute', inset: -2 - normalizedVol * 8,
              borderRadius: '50%',
              background: v.activity === 'lara-speaking'
                ? 'var(--sb-accent)'
                : 'var(--sb-hot)',
              opacity: 0.15 + normalizedVol * 0.35,
              transition: 'all 80ms ease-out',
              pointerEvents: 'none',
            }} />
          )}
          <SBIcon name="mic" size={14} />
        </button>
        <button
          onClick={submit}
          disabled={!canSend}
          aria-label="Send"
          style={{
            background: canSend ? 'var(--sb-accent)' : 'var(--sb-card)',
            color: canSend ? '#000' : 'var(--sb-fg-5)',
            border: 'none', padding: '7px 10px',
            cursor: canSend ? 'pointer' : 'not-allowed',
            display: 'flex', alignItems: 'center',
          }}
        >
          <SBIcon name="send" size={13} />
        </button>
      </div>

      <div style={{
        display: 'flex', justifyContent: 'space-between', marginTop: 8,
        fontSize: 10.5, fontFamily: 'var(--sb-font-mono)', color: 'var(--sb-fg-5)',
      }}>
        <span>
          <SBKbd>/</SBKbd> commands · <SBKbd>@</SBKbd> mention · <SBKbd>⏎</SBKbd> send
        </span>
        <span>
          {v.state === 'listening' && v.activity === 'user-speaking' && (
            <span style={{ color: 'var(--sb-hot)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              ● you · speaking
              <span style={{
                display: 'inline-block', width: 40, height: 4,
                background: 'var(--sb-line-2)', borderRadius: 2, overflow: 'hidden',
              }}>
                <span style={{
                  display: 'block', height: '100%', borderRadius: 2,
                  background: 'var(--sb-hot)',
                  width: `${normalizedVol * 100}%`,
                  transition: 'width 80ms ease-out',
                }} />
              </span>
            </span>
          )}
          {v.state === 'listening' && v.activity === 'lara-speaking' && (
            <span style={{ color: 'var(--sb-accent)' }}>◆ lara · speaking</span>
          )}
          {v.state === 'listening' && v.activity === 'quiet' && (
            <span style={{ color: 'var(--sb-fg-4)' }}>○ live · click mic to stop</span>
          )}
          {v.state === 'connecting' && <span style={{ color: 'var(--sb-warm)' }}>connecting voice…</span>}
          {v.state === 'error' && <span style={{ color: 'var(--sb-hot)' }}>voice: {v.error?.message || 'error'}</span>}
          {v.state === 'idle' && <span>SSE · data-stream v1</span>}
        </span>
      </div>
    </div>
  );
}
