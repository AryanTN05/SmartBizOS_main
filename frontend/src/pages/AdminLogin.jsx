import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SBButton, SBCard } from '../components/primitives';
import { useSession } from '../lib/SessionContext.jsx';

const ERROR_COPY = {
  bad_credentials: 'Email or password is incorrect.',
  rate_limited:    'Too many attempts. Try again in a few minutes.',
  validation_failed: 'Check your email and password format.',
  network_unreachable: 'Backend unreachable. Is the API running on :8000?',
};

export default function AdminLogin() {
  const navigate = useNavigate();
  const { session, login } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (session?.kind === 'admin') navigate('/admin', { replace: true });
  }, [session, navigate]);

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(email, password);
      navigate('/admin', { replace: true });
    } catch (x) {
      setErr(x.code || 'internal');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <SBCard bracket style={{ padding: 36, maxWidth: 420, width: '100%' }}>
        <div className="sb-label" style={{ color: 'var(--sb-accent)', marginBottom: 10 }}>Admin</div>
        <h1 style={{ margin: 0, fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 500, letterSpacing: '-0.02em' }}>
          Sign in
        </h1>
        <p style={{ marginTop: 10, color: 'var(--sb-fg-4)', fontSize: 13 }}>
          Team accounts only. Demo visitors don't need this.
        </p>

        <form onSubmit={onSubmit} style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Field label="email">
            <input
              type="email"
              autoComplete="email"
              autoFocus
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
            />
          </Field>
          <Field label="password">
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={inputStyle}
            />
          </Field>

          {err && (
            <div style={{
              fontFamily: 'var(--sb-font-mono)', fontSize: 11,
              color: 'var(--sb-hot)', border: '1px solid var(--sb-hot)',
              padding: '8px 10px', whiteSpace: 'pre-wrap',
            }}>
              ▸ {ERROR_COPY[err] || 'Something went wrong.'}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <SBButton type="submit" variant="primary" icon="arrow" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </SBButton>
            <SBButton variant="ghost" onClick={() => navigate('/')}>Back</SBButton>
          </div>
        </form>
      </SBCard>
    </div>
  );
}

const inputStyle = {
  width: '100%', padding: '10px 12px', fontSize: 13,
  background: 'var(--sb-panel)', color: 'var(--sb-fg)',
  border: '1px solid var(--sb-line-2)', outline: 'none',
  fontFamily: 'var(--sb-font)',
};

function Field({ label, children }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span className="sb-label">{label}</span>
      {children}
    </label>
  );
}
