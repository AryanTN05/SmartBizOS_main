import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../lib/api.js';
import { useSessionContext } from '../../lib/SessionContext.jsx';

// Internal streaming chat hook.
//
// We're pinned to @ai-sdk/react v1.2.x in package.json, which does NOT ship
// `DefaultChatTransport` (that's v7). Rather than force-upgrade, we hand-roll
// the AI SDK data-stream protocol v1 parser — the wire format is small and
// the backend spec is fixed. This keeps the dep surface small.
//
// Messages in our local shape:
//   { role: 'user', text }
//   { role: 'lara', parts: [{ kind, ... }] }
// where `parts` entries are one of:
//   { kind: 'text', text }
//   { kind: 'tool', id, name, args, result?, error?, status }  // status: 'input'|'running'|'done'|'error'
//   { kind: 'leads', items: [...] }      // synthesized from crm__list_hot_leads output

export const LEAD_TOOL = 'get_leads';

export function useLaraChat({ conversationId: initialConvId = null, seedMessages = [] } = {}) {
  const navigate = useNavigate();
  const { session, refresh } = useSessionContext();

  const [messages, setMessages] = useState(seedMessages);
  const [thinking, setThinking] = useState(false);
  // Mint a fresh conversation_id per hook instance when none was passed in.
  // Without this, the backend buckets every admin chat under `admin:{uid}`
  // and the Conversations list shows one giant merged blob. Each drawer
  // open / Leads-handoff / full-page mount becomes its own thread.
  const [conversationId, setConversationId] = useState(
    () => initialConvId || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `chat-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`)
  );
  const [tokensUsed, setTokensUsed] = useState(0); // accumulated across the session
  const abortRef = useRef(null);
  // Mirror messages into a ref so `send` can serialize the latest history
  // without listing `messages` as a dep — that dep was causing send (and the
  // entire handleEvent → consumeDataStream chain) to be recreated on every
  // text-delta state update, which in turn caused thrash + missed re-renders.
  const messagesRef = useRef(messages);
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  // We deliberately don't abort the in-flight stream on unmount: in dev,
  // React.StrictMode mounts/unmounts/remounts components, and aborting here
  // killed the seed-prompt fetch every time the drawer opened. The Stop
  // button (`stop()` below) gives the user explicit control instead.

  // Append a part to the in-flight assistant message (creates one if needed).
  const appendAssistantPart = useCallback((updater) => {
    setMessages((prev) => {
      const next = prev.slice();
      let last = next[next.length - 1];
      if (!last || last.role !== 'lara' || last._final) {
        last = { role: 'lara', parts: [], _inflight: true };
        next.push(last);
      } else {
        last = { ...last, parts: last.parts.slice() };
        next[next.length - 1] = last;
      }
      updater(last);
      return next;
    });
  }, []);

  const finalizeAssistant = useCallback(() => {
    setMessages((prev) => {
      if (!prev.length) return prev;
      const next = prev.slice();
      const last = next[next.length - 1];
      if (last && last.role === 'lara' && last._inflight) {
        next[next.length - 1] = { ...last, _inflight: false, _final: true };
      }
      return next;
    });
  }, []);

  const handleEvent = useCallback((ev) => {
    if (!ev || !ev.type) return;

    switch (ev.type) {
      case 'text-delta': {
        appendAssistantPart((msg) => {
          const last = msg.parts[msg.parts.length - 1];
          if (last && last.kind === 'text' && !last._locked) {
            last.text = (last.text || '') + (ev.delta || '');
          } else {
            msg.parts.push({ kind: 'text', text: ev.delta || '' });
          }
        });
        break;
      }
      case 'tool-input-start': {
        appendAssistantPart((msg) => {
          // Close any trailing streaming text part so new text lands below the tool.
          const last = msg.parts[msg.parts.length - 1];
          if (last && last.kind === 'text') last._locked = true;
          msg.parts.push({
            kind: 'tool', id: ev.toolCallId, name: ev.toolName,
            args: '', _argsJson: '', status: 'input',
          });
        });
        break;
      }
      case 'tool-input-delta': {
        appendAssistantPart((msg) => {
          const tool = msg.parts.find((p) => p.kind === 'tool' && p.id === ev.toolCallId);
          if (tool) {
            tool._argsJson = (tool._argsJson || '') + (ev.inputTextDelta || '');
            tool.args = tool._argsJson;
          }
        });
        break;
      }
      case 'tool-input-available': {
        appendAssistantPart((msg) => {
          const tool = msg.parts.find((p) => p.kind === 'tool' && p.id === ev.toolCallId);
          if (tool) {
            tool.args = prettyArgs(ev.input);
            tool.status = 'running';
          } else {
            msg.parts.push({
              kind: 'tool', id: ev.toolCallId, name: ev.toolName,
              args: prettyArgs(ev.input), status: 'running',
            });
          }
        });
        break;
      }
      case 'tool-output-available': {
        appendAssistantPart((msg) => {
          const tool = msg.parts.find((p) => p.kind === 'tool' && p.id === ev.toolCallId);
          if (tool) {
            tool.status = 'done';
            
            if (tool.name === 'create_lead' || tool.name === 'update_lead') {
              window.dispatchEvent(new CustomEvent('lara:lead_updated'));
            }
            
            let parsedOutput = ev.output;
            if (typeof ev.output === 'string') {
              try {
                parsedOutput = JSON.parse(ev.output);
              } catch (_) {}
            }

            tool.result = summarizeResult(tool.name, parsedOutput);
            // If this is the hot-leads tool, attach a lead card right after.
            if (tool.name === LEAD_TOOL || tool.name === 'get_lead_dossier') {
              let arr = Array.isArray(parsedOutput) ? parsedOutput : (parsedOutput?.items || parsedOutput?.leads || [parsedOutput]);
              
              // Handle case where parsedOutput is a JSON string (double encoded)
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
                msg.parts.push({ kind: 'leads', items });
              }
            }
            
            if (tool.name === 'web_search') {
              let searchResult = parsedOutput;
              
              // Handle case where parsedOutput is a JSON string (double encoded)
              if (typeof searchResult === 'string') {
                try {
                  searchResult = JSON.parse(searchResult);
                } catch (_) {}
              }
              
              if (typeof searchResult === 'object' && searchResult.results) {
                searchResult = searchResult.results;
              }
              // Format web search result as a text artifact
              msg.parts.push({ kind: 'artifact', artifact_type: 'table', content: `<div style="white-space: pre-wrap; font-family: var(--sb-font-sans); line-height: 1.5;">${searchResult}</div>` });
            }
            
            if (tool.name === 'show_artifact') {
              try {
                const args = JSON.parse(tool._argsJson || tool.args || '{}');
                if (args.url) msg.parts.push({ kind: 'artifact', artifact_type: 'url', content: args.url });
                if (args.table) msg.parts.push({ kind: 'artifact', artifact_type: 'table', content: args.table });
                if (args.charts) msg.parts.push({ kind: 'artifact', artifact_type: 'charts', content: args.charts });
              } catch (_) {}
            }
          }
        });
        break;
      }
      case 'tool-output-error': {
        appendAssistantPart((msg) => {
          const tool = msg.parts.find((p) => p.kind === 'tool' && p.id === ev.toolCallId);
          if (tool) {
            tool.status = 'error';
            tool.error = ev.errorText || 'tool failed';
          }
        });
        break;
      }
      case 'data-session': {
        // Server emits {tokens_used: N} after each turn (real LiteLLM count).
        const d = ev.data || {};
        if (typeof d.tokens_used === 'number') {
          setTokensUsed((prev) => prev + d.tokens_used);
        }
        break;
      }
      case 'data-cutoff': {
        const reason = ev.data?.reason || 'demo_expired';
        try { sessionStorage.setItem('sb:expired_reason', reason); } catch (_) { /* no-op */ }
        navigate('/expired');
        break;
      }
      case 'finish': {
        finalizeAssistant();
        setThinking(false);
        // Best-effort refresh of session counters from server truth.
        try { refresh(); } catch (_) { /* no-op */ }
        // Tell ConversationsList to refetch — the chat just persisted a turn.
        try { window.dispatchEvent(new CustomEvent('lara:conversation_added')); } catch (_) { /* no-op */ }
        break;
      }
      case 'error': {
        appendAssistantPart((msg) => {
          msg.parts.push({ kind: 'text', text: `⚠ ${ev.errorText || 'stream error'}` });
        });
        finalizeAssistant();
        setThinking(false);
        break;
      }
      default:
        break;
    }
  }, [appendAssistantPart, finalizeAssistant, navigate, refresh, session]);

  const send = useCallback(async (text) => {
    const trimmed = (text || '').trim();
    if (!trimmed) return;

    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setThinking(true);

    const body = {
      messages: [
        ...serializeForWire(messagesRef.current),
        { role: 'user', content: trimmed },
      ],
      conversation_id: conversationId,
      options: { voice_mode: false, language: 'en' },
    };

    const controller = new AbortController();
    abortRef.current = controller;

    const showError = (text) => {
      appendAssistantPart((msg) => msg.parts.push({ kind: 'text', text: `⚠ ${text}` }));
      finalizeAssistant();
      setThinking(false);
    };

    let res;
    try {
      res = await api.stream('/api/stream/chat', body, { signal: controller.signal });
    } catch (e) {
      if (e?.name === 'AbortError') { setThinking(false); return; }
      showError('Network error — backend unreachable.');
      return;
    }

    if (!res.ok || !res.body) {
      showError(`Request failed (${res.status}).`);
      return;
    }

    try {
      await consumeDataStream(res.body, handleEvent);
    } catch (e) {
      if (e?.name === 'AbortError') { setThinking(false); return; }
      showError('Stream interrupted.');
      return;
    }

    // Safety net if backend forgets to emit `finish`.
    finalizeAssistant();
    setThinking(false);
  }, [appendAssistantPart, conversationId, finalizeAssistant, handleEvent]);

  const stop = useCallback(() => {
    abortRef.current?.abort?.();
    setThinking(false);
  }, []);

  return { messages, thinking, send, stop, conversationId, tokensUsed, setMessages, setConversationId };
}

// ─── helpers ─────────────────────────────────────────────────────────────────

function prettyArgs(input) {
  if (input == null) return '{}';
  try {
    const s = typeof input === 'string' ? input : JSON.stringify(input);
    // Chop extremely long arg blobs — the UI is mono-line.
    return s.length > 120 ? s.slice(0, 117) + '…' : s;
  } catch (_) { return String(input); }
}

export function summarizeResult(toolName, output) {
  if (output == null) return 'ok';
  if (toolName === LEAD_TOOL || toolName === 'get_lead_dossier') {
    let arr = Array.isArray(output) ? output : (output.items || output.leads || [output]);
    if (typeof arr === 'string') {
      try {
        const innerParsed = JSON.parse(arr);
        arr = Array.isArray(innerParsed) ? innerParsed : (innerParsed?.items || innerParsed?.leads || [innerParsed]);
      } catch (_) {}
    }
    const scores = Array.isArray(arr) ? arr.map((l) => l.score).filter((s) => s != null).join(', ') : '';
    const len = Array.isArray(arr) ? arr.length : 0;
    return `${len} lead${len === 1 ? '' : 's'}${scores ? ' · scores ' + scores : ''}`;
  }
  if (toolName === 'web_search') {
    return 'Search completed';
  }
  if (typeof output === 'string') return output.length > 80 ? output.slice(0, 77) + '…' : output;
  if (output.message) return String(output.message);
  if (output.summary) return String(output.summary);
  try {
    const s = JSON.stringify(output);
    return s.length > 80 ? s.slice(0, 77) + '…' : s;
  } catch (_) { return 'ok'; }
}

// Flatten our `{role, parts}` messages into the AI SDK wire shape. Seed
// entries become assistant text; tool parts are dropped (server will replay
// them from persisted state when conversation_id is set).
function serializeForWire(msgs) {
  return msgs.map((m) => {
    if (m.role === 'user') return { role: 'user', content: m.text || '' };
    const text = (m.parts || [])
      .filter((p) => p.kind === 'text')
      .map((p) => p.text)
      .join('\n');
    return { role: 'assistant', content: text };
  }).filter((m) => m.content != null);
}

// Parse an SSE / NDJSON stream into AI SDK data-stream events.
//
// Backend sends `Content-Type: text/event-stream`, each event like:
//   data: {"type":"text-delta","delta":"hi"}\n\n
// We tolerate both SSE `data:` framing and line-delimited JSON so any small
// backend deviation still works during V0.
async function consumeDataStream(stream, onEvent) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Split on SSE event boundary (blank line) OR newline — whichever matches.
    while (true) {
      const boundary = buffer.indexOf('\n\n');
      const newline  = buffer.indexOf('\n');
      if (boundary === -1 && newline === -1) break;

      const cut = boundary !== -1 ? boundary + 2 : newline + 1;
      const chunk = buffer.slice(0, boundary !== -1 ? boundary : newline).trim();
      buffer = buffer.slice(cut);
      if (!chunk) continue;

      // Strip any `data:` SSE prefixes and concatenate multi-line data.
      const payload = chunk
        .split('\n')
        .map((ln) => ln.startsWith('data:') ? ln.slice(5).trim() : ln.trim())
        .filter(Boolean)
        .join('');
      if (!payload || payload === '[DONE]') continue;

      try {
        const ev = JSON.parse(payload);
        onEvent(ev);
      } catch (_) {
        // Ignore malformed frames — don't kill the stream.
      }
    }
  }
}
