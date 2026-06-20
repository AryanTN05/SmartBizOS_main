import React from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBCard } from '../components/primitives';

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <SBCard bracket style={{ padding: 36, maxWidth: 420, width: '100%' }}>
        <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 10 }}>404</div>
        <h1 style={{ margin: 0, fontFamily: 'var(--sb-font-display)', fontSize: 34, fontWeight: 500, letterSpacing: '-0.03em' }}>
          Nothing here.
        </h1>
        <p style={{ marginTop: 10, color: 'var(--sb-fg-4)', fontSize: 13 }}>
          Either the URL was wrong or the module hasn't shipped yet.
        </p>
        <div style={{ marginTop: 20 }}>
          <SBButton variant="primary" icon="arrow" onClick={() => navigate('/')}>Back to start</SBButton>
        </div>
      </SBCard>
    </div>
  );
}
