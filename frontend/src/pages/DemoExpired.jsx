import React from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBCard } from '../components/primitives';

const REASONS = {
  time:   'Your 5 minutes are up.',
  tokens: 'You hit the 2000-token demo cap.',
  default: 'Session ended.',
};

export default function DemoExpired() {
  const navigate = useNavigate();
  const reasonKey = typeof window !== 'undefined' ? sessionStorage.getItem('sb-expired-reason') : null;
  const line = REASONS[reasonKey] || REASONS.default;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <SBCard bracket style={{ padding: 36, maxWidth: 480, width: '100%' }}>
        <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 14 }}>Session complete</div>
        <h1 style={{ margin: 0, fontFamily: 'var(--sb-font-display)', fontSize: 34, fontWeight: 500, letterSpacing: '-0.03em', lineHeight: 1.05 }}>
          {line}
        </h1>
        <p style={{ marginTop: 14, color: 'var(--sb-fg-3)', fontSize: 14, lineHeight: 1.6 }}>
          Want to see what a real deployment looks like? Book a call — we'll
          build one for your business in days, not quarters.
        </p>

        <div style={{ display: 'flex', gap: 8, marginTop: 22 }}>
          <SBButton
            variant="primary"
            icon="bolt"
            onClick={() => window.open('https://cal.com/zerotoprod/30min', '_blank', 'noopener')}
          >
            Book a call
          </SBButton>
          <SBButton variant="ghost" onClick={() => navigate('/')}>Back to start</SBButton>
        </div>
      </SBCard>
    </div>
  );
}
