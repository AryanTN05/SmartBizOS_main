import React from 'react';
import { SBIcon } from '../../../components/primitives';

// A single tool invocation block inside an assistant turn.
// `part` shape (from useLaraChat):
//   { kind: 'tool', name, args, result?, error?, status: 'input'|'running'|'done'|'error' }
// The seeded fallback uses `status` undefined + a result string — treat that as 'done'.
export default function ToolCallCard({ part }) {
  const status = part.status || (part.error ? 'error' : part.result ? 'done' : 'running');

  return (
    <div style={{
      fontFamily: 'var(--sb-font-mono)', fontSize: 11,
      border: '1px solid var(--sb-line)', background: 'var(--sb-bg-2)',
    }}>
      <div style={{
        padding: '6px 10px', borderBottom: '1px solid var(--sb-line)',
        display: 'flex', alignItems: 'center', gap: 6, color: 'var(--sb-violet)',
      }}>
        <SBIcon name="tool" size={11} stroke={1.6} />
        <span style={{ fontWeight: 700 }}>{part.name}</span>
        <span style={{
          color: 'var(--sb-fg-5)', marginLeft: 'auto', whiteSpace: 'nowrap',
          overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '60%',
        }}>
          {part.args || '{}'}
        </span>
      </div>
      <div style={{ padding: '6px 10px', display: 'flex', alignItems: 'center', gap: 6 }}>
        {status === 'running' && (
          <span style={{ color: 'var(--sb-fg-4)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Dot /> running…
          </span>
        )}
        {status === 'input' && (
          <span style={{ color: 'var(--sb-fg-5)' }}>preparing args…</span>
        )}
        {status === 'done' && (
          <span style={{ color: 'var(--sb-accent)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <SBIcon name="check" size={10} stroke={2} /> {part.result || 'ok'}
          </span>
        )}
        {status === 'error' && (
          <span style={{ color: 'var(--sb-hot)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <SBIcon name="warn" size={10} stroke={2} /> {part.error || 'tool failed'}
          </span>
        )}
      </div>
    </div>
  );
}

function Dot() {
  return (
    <span style={{
      width: 5, height: 5, borderRadius: '50%', background: 'var(--sb-accent)',
      animation: 'sb-bounce 1.4s infinite',
    }} />
  );
}
