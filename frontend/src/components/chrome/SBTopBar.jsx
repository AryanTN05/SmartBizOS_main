import React from 'react';
import DemoCountdown from './DemoCountdown.jsx';
import { useSession } from '../../lib/SessionContext.jsx';

export default function SBTopBar({ title, crumb = [], children }) {
  const { session } = useSession();
  const demo = session?.kind === 'demo';
  return (
    <header style={{
      padding: '14px 28px', borderBottom: '1px solid var(--sb-line)',
      background: 'var(--sb-bg)', position: 'sticky', top: 0, zIndex: 10,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20,
    }}>
      <div style={{ minWidth: 0, flex: 1, display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{
          fontSize: 11, fontFamily: 'var(--sb-font-mono)', color: 'var(--sb-fg-5)',
          letterSpacing: '0.12em', textTransform: 'uppercase',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0,
        }}>
          {crumb.map((c, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span style={{ color: 'var(--sb-fg-6)', margin: '0 6px' }}>/</span>}
              <span style={{ color: i === crumb.length - 1 ? 'var(--sb-fg-3)' : 'var(--sb-fg-5)' }}>{c}</span>
            </React.Fragment>
          ))}
        </div>
        <h1 style={{
          margin: 0, fontSize: 16, fontWeight: 600,
          fontFamily: 'var(--sb-font-display)', letterSpacing: '-0.01em',
        }}>{title}</h1>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {children}
        {demo && <DemoCountdown />}
      </div>
    </header>
  );
}
