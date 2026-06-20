import React from 'react';
import { SBIcon } from '../../../components/primitives';
import ToolCallCard from './ToolCallCard.jsx';
import LeadResultCard from './LeadResultCard.jsx';
import ArtifactCard from './ArtifactCard.jsx';

// A single message in the stream. User messages are right-aligned cards.
// Assistant ("lara") messages render their `parts[]` inline: text, tool
// cards, lead cards — in order.
export default function Message({ m }) {
  if (m.role === 'user') {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 18 }}>
        <div style={{
          maxWidth: '80%', background: 'var(--sb-card)',
          border: '1px solid var(--sb-line-2)',
          padding: '10px 14px', fontSize: 13, lineHeight: 1.55, color: 'var(--sb-fg)',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        }}>{m.text}</div>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 22, display: 'flex', gap: 10 }}>
      <div style={{
        width: 24, height: 24, background: 'var(--sb-accent-bg)',
        color: 'var(--sb-accent)', display: 'flex', alignItems: 'center',
        justifyContent: 'center', flexShrink: 0, marginTop: 2,
      }}>
        <SBIcon name="lara" size={13} stroke={1.5} />
      </div>
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0,
      }}>
        {(m.parts || []).map((p, i) => <MessagePart key={i} p={p} />)}
      </div>
    </div>
  );
}

function MessagePart({ p }) {
  if (p.kind === 'text') {
    return (
      <div style={{
        fontSize: 13.5, lineHeight: 1.6, color: 'var(--sb-fg-2)',
        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
      }}>{p.text}</div>
    );
  }
  if (p.kind === 'tool')  return <ToolCallCard part={p} />;
  if (p.kind === 'leads') return <LeadResultCard items={p.items} />;
  if (p.kind === 'artifact') return <ArtifactCard part={p} />;
  return null;
}
