import React from 'react';
import { SBIcon } from '../../../components/primitives';

// Muted banner shown above a list when we fell back to seed data.
// `code` is the ApiError.code so power users can tell "unauthenticated" from
// "network_unreachable" at a glance.
export default function OfflineBanner({ code, hint }) {
  const isAuth = code === 'unauthenticated' || code === 'forbidden';
  return (
    <div style={{
      padding: '8px 20px', background: 'var(--sb-panel)',
      borderBottom: '1px solid var(--sb-line-2)',
      display: 'flex', alignItems: 'center', gap: 8,
      fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-4)',
    }}>
      <SBIcon name="warn" size={12} stroke={1.6} />
      <span>
        {isAuth
          ? 'Auth required — showing seed data.'
          : 'Backend offline — showing seed data.'}
        {hint ? <span style={{ color: 'var(--sb-fg-5)', marginLeft: 8 }}>({hint})</span> : null}
      </span>
    </div>
  );
}
