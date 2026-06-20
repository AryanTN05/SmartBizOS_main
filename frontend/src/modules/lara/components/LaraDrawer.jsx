import React, { useEffect, useRef } from 'react';
import { SBIcon } from '../../../components/primitives';
import { useSession } from '../../../lib/SessionContext.jsx';
import { useLaraChat, summarizeResult, LEAD_TOOL } from '../useLaraChat.js';
import { useVoiceSession } from '../useVoiceSession.js';
import MessageStream from './MessageStream.jsx';
import Composer from './Composer.jsx';

// The real Lara drawer body. Rendered inside `LaraDrawerShell` which
// owns the backdrop + panel animation. Variants:
//   variant="drawer" (default) — slim side-panel chrome.
//   variant="page"             — full-bleed chrome for the /lara full page.
export default function LaraDrawer({ seed, onClose, variant = 'drawer', showHeader = true }) {
  const { session } = useSession();
  const { messages, thinking, send, setMessages, tokensUsed } = useLaraChat();
  const voice = useVoiceSession();

  // Project voice transcripts into the chat history. Voice IS the LLM, so we
  // append directly via setMessages rather than firing /api/stream/chat again.
  //
  // Gemini streams transcripts in small chunks (often a few words at a time).
  // We coalesce same-role chunks into a single bubble per turn — a user
  // bubble is "open" until the assistant starts replying (or turn_end), and
  // an assistant bubble is "open" until the user starts speaking (or turn_end).
  const projectedRef = useRef(0);
  const openTurnRef = useRef(null); // { role: 'user'|'lara', messageIndex }
  useEffect(() => {
    const next = voice.events.slice(projectedRef.current);
    if (next.length === 0) return;
    projectedRef.current = voice.events.length;

    setMessages((prev) => {
      const out = prev.slice();

      const appendText = (role, text) => {
        const turn = openTurnRef.current;
        if (turn && turn.role === role && out[turn.messageIndex]?.role === (role === 'user' ? 'user' : 'lara')) {
          const msg = { ...out[turn.messageIndex] };
          if (role === 'user') {
            msg.text = (msg.text || '') + text;
          } else {
            msg.parts = (msg.parts || []).slice();
            const last = msg.parts[msg.parts.length - 1];
            if (last && last.kind === 'text') {
              msg.parts[msg.parts.length - 1] = { ...last, text: (last.text || '') + text };
            } else {
              msg.parts.push({ kind: 'text', text });
            }
          }
          out[turn.messageIndex] = msg;
        } else {
          if (role === 'user') {
            out.push({ role: 'user', text });
          } else {
            out.push({ role: 'lara', _final: true, parts: [{ kind: 'text', text }] });
          }
          openTurnRef.current = { role, messageIndex: out.length - 1 };
        }
      };

      for (const ev of next) {
        if (ev.type === 'transcript' && ev.text) {
          if (ev.role === 'user' || ev.role === 'assistant') {
            appendText(ev.role === 'user' ? 'user' : 'lara', ev.text);
          }
        } else if (ev.type === 'turn_end') {
          openTurnRef.current = null;
          // Backend flushed this turn's user/assistant transcripts to the DB
          // on turn_complete — nudge ConversationsList to refetch.
          try { window.dispatchEvent(new CustomEvent('lara:conversation_added')); } catch (_) { /* no-op */ }
        } else if (ev.type === 'tool_result' && ev.tool) {
          if (ev.tool === 'create_lead' || ev.tool === 'update_lead') {
            window.dispatchEvent(new CustomEvent('lara:lead_updated'));
          }
          let parsedOutput = ev.result;
          if (typeof ev.result === 'string') {
            try {
              parsedOutput = JSON.parse(ev.result);
            } catch (_) {}
          }
          
          const parts = [{
            kind: 'tool', name: ev.tool,
            args: '', status: 'done',
            result: summarizeResult(ev.tool, parsedOutput),
          }];
          
          if (ev.tool === LEAD_TOOL || ev.tool === 'get_lead_dossier') {
            let arr = Array.isArray(parsedOutput) ? parsedOutput : (parsedOutput?.items || parsedOutput?.leads || [parsedOutput]);
            if (typeof arr === 'string') {
              try {
                const innerParsed = JSON.parse(arr);
                arr = Array.isArray(innerParsed) ? innerParsed : (innerParsed?.items || innerParsed?.leads || [innerParsed]);
              } catch (_) {}
            }
            if (Array.isArray(arr)) {
              const items = arr.map((l) => ({
                name: l.name, co: l.company || l.company_name || l.co || '',
                score: l.score, why: l.reason || l.why || '',
                status: l.status || ''
              }));
              parts.push({ kind: 'leads', items });
            }
          }
          
          if (ev.tool === 'web_search') {
            let searchResult = parsedOutput;
            if (typeof searchResult === 'string') {
              try {
                searchResult = JSON.parse(searchResult);
              } catch (_) {}
            }
            if (typeof searchResult === 'object' && searchResult.results) {
              searchResult = searchResult.results;
            }
            parts.push({ kind: 'artifact', artifact_type: 'table', content: `<div style="white-space: pre-wrap; font-family: var(--sb-font-sans); line-height: 1.5;">${searchResult}</div>` });
          }

          out.push({
            role: 'lara', _final: true,
            parts: parts,
          });
          openTurnRef.current = null;
        } else if (ev.type === 'artifact') {
          out.push({
            role: 'lara', _final: true,
            parts: [{
              kind: 'artifact',
              artifact_type: ev.artifact_type,
              content: ev.content
            }],
          });
          openTurnRef.current = null;
        }
      }
      return out;
    });
  }, [voice.events, setMessages]);

  // If the caller passed a seed payload with a prompt (e.g., from "Yes, do it"
  // CTAs on the admin home), fire it once on mount. Guarded with a ref because
  // React.StrictMode runs effects twice in dev — without this we'd send the
  // prompt twice and race two streams into the same in-flight bubble.
  const sentSeedRef = useRef(false);
  useEffect(() => {
    if (sentSeedRef.current) return;
    if (seed?.prompt && typeof seed.prompt === 'string') {
      sentSeedRef.current = true;
      send(seed.prompt);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Real LiteLLM token usage accumulates across the session via the
  // data-session frame. tokensUsed sums prompt+completion across every turn.
  const tokensLimit = 8000;

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      background: variant === 'page' ? 'var(--sb-bg)' : 'var(--sb-bg-2)',
    }}>
      {showHeader && (
        <div style={{
          padding: '14px 20px', borderBottom: '1px solid var(--sb-line)',
          display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
        }}>
          <div style={{
            position: 'relative', width: 32, height: 32,
            background: 'var(--sb-accent-bg)', color: 'var(--sb-accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <SBIcon name="lara" size={18} stroke={1.3} />
            <div style={{
              position: 'absolute', inset: -2,
              border: '1px solid var(--sb-accent)', opacity: 0.3,
              animation: 'sb-ping 2s infinite',
            }} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 14, fontWeight: 600, fontFamily: 'var(--sb-font-display)',
            }}>Lara</div>
            <div style={{
              fontSize: 10.5, fontFamily: 'var(--sb-font-mono)',
              color: 'var(--sb-fg-5)', letterSpacing: '0.1em',
            }}>
              haiku-4.5 · 8 tools connected
            </div>
          </div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '3px 8px', background: 'var(--sb-panel)',
            fontSize: 10.5, fontFamily: 'var(--sb-font-mono)', color: 'var(--sb-fg-4)',
          }}>
            <span style={{ color: 'var(--sb-accent)' }}>
              {tokensUsed || 0}
            </span>
            /{tokensLimit} tok
          </div>
          {onClose && (
            <button
              onClick={onClose}
              aria-label="Close Lara"
              style={{
                background: 'transparent', border: 'none', color: 'var(--sb-fg-4)',
                cursor: 'pointer', padding: 4,
              }}
            >
              <SBIcon name="close" size={16} />
            </button>
          )}
        </div>
      )}

      <MessageStream
        messages={messages}
        thinking={thinking}
        padding={variant === 'page' ? '24px 32px 16px' : '20px 20px 12px'}
      />

      <Composer onSend={send} voice={voice} />
    </div>
  );
}
