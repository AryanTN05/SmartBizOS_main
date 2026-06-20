import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { SBButton, SBChip } from '../../../components/primitives';
import api from '../../../lib/api.js';
import EmptyState from '../components/EmptyState.jsx';
import ToolCallCard from '../components/ToolCallCard.jsx';

// Read-only transcript of a persisted conversation. Tool calls are shown
// expanded (their args + results) so the admin can audit what Lara did.
export default function ConversationDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null); // null=loading, false=error, object=ok

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get(`/api/conversations/${encodeURIComponent(id)}`);
        if (!cancelled) setData(r);
      } catch (e) {
        if (!cancelled) setData(false);
      }
    })();
    return () => { cancelled = true; };
  }, [id]);

  if (data === null) {
    return (
      <div style={{ padding: '28px 32px', color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', fontSize: 12 }}>
        loading…
      </div>
    );
  }
  if (data === false) {
    return (
      <div style={{ padding: '28px 32px' }}>
        <SBButton variant="ghost" size="sm" icon="arrowDown" onClick={() => navigate('/admin/conversations')}>
          Back
        </SBButton>
        <div style={{ marginTop: 16 }}>
          <EmptyState title="Conversation not found" detail="Either the backend is offline, or this id doesn't exist." />
        </div>
      </div>
    );
  }

  const { conversation, messages = [] } = data;

  return (
    <div style={{ padding: '28px 32px' }}>
      <SBButton variant="ghost" size="sm" onClick={() => navigate('/admin/conversations')}>
        ← Conversations
      </SBButton>

      <div style={{ marginTop: 16, marginBottom: 24 }}>
        <div className="sb-label">Conversation</div>
        <h1 style={{
          fontFamily: 'var(--sb-font-display)', fontSize: 24, fontWeight: 500,
          margin: '6px 0 10px', letterSpacing: '-0.02em',
        }}>{conversation?.title || 'Untitled'}</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <SBChip tone={conversation?.kind === 'admin' ? 'accent' : 'violet'}>
            {conversation?.kind || 'unknown'}
          </SBChip>
          <span style={{
            fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
          }}>
            {messages.length} messages
          </span>
        </div>
      </div>

      <div style={{
        border: '1px solid var(--sb-line)', background: 'var(--sb-card)',
        padding: 20, display: 'flex', flexDirection: 'column', gap: 18,
      }}>
        {messages.length === 0 && (
          <EmptyState title="Empty transcript" detail="No messages on this conversation." />
        )}
        {messages.map((m) => (
          <TranscriptRow key={m.id} m={m} />
        ))}
      </div>
    </div>
  );
}

function TranscriptRow({ m }) {
  const isUser = m.role === 'user';
  return (
    <div>
      <div style={{
        fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.15em',
        fontFamily: 'var(--sb-font-mono)', color: 'var(--sb-fg-5)', marginBottom: 6,
      }}>
        {m.role}
      </div>
      {m.content && (
        <div style={{
          fontSize: 13.5, lineHeight: 1.6,
          color: isUser ? 'var(--sb-fg)' : 'var(--sb-fg-2)',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        }}>{m.content}</div>
      )}
      {Array.isArray(m.tool_calls) && m.tool_calls.length > 0 && (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {m.tool_calls.map((tc) => (
            <ToolCallCard
              key={tc.id}
              part={{
                kind: 'tool',
                id: tc.id, name: tc.name,
                args: typeof tc.args === 'string' ? tc.args : JSON.stringify(tc.args),
                result: tc.result ? (typeof tc.result === 'string' ? tc.result : 'ok') : null,
                error: tc.error || null,
                status: tc.error ? 'error' : (tc.result ? 'done' : 'running'),
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
