import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import api from './api.js';

// ─────────────────────────────────────────────────────────────────────────────
// Session + config context.
//
// `session` mirrors GET /api/session/me: { kind: "demo" | "admin" | "anon", ... }
// `config`  mirrors GET /api/config:     { version, environment, features, demo_limits }
//
// Backend may be down in V0 dev. In that case we degrade to:
//   session = { kind: "anon" }
//   config  = FALLBACK_CONFIG
// and keep the UI usable. Module agents should read from here via
// `useSession()` / `useConfig()` and NEVER block on a loading state beyond
// the initial boot.
// ─────────────────────────────────────────────────────────────────────────────

const FALLBACK_CONFIG = {
  version: '0.0.0-dev',
  environment: 'dev',
  features: {
    voice_enabled: false,
    hindi_voice_enabled: false,
    m7_fintech_enabled: false,
    scraper_live_enabled: false,
  },
  demo_limits: {
    session_seconds: 300,
    session_tokens: 2000,
    ip_rate_limit_per_hour: 1,
  },
};

// V0 dev bypass: with backend absent, default to a faux admin session so the
// full admin UI is walkable. Flip via VITE_AUTH_BYPASS=0 to restore anon.
const AUTH_BYPASS = import.meta.env.VITE_AUTH_BYPASS !== '0';

const FALLBACK_SESSION = AUTH_BYPASS
  ? {
      kind: 'admin',
      admin: {
        id: '00000000-0000-0000-0000-000000000001',
        email: 'dev@zerotoprod.tech',
        name: 'Ravi Shankar',
        role: 'admin',
        status: 'active',
        created_at_unix: 0,
        last_login_at_unix: null,
      },
    }
  : { kind: 'anon' };

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  const [session, setSession] = useState(FALLBACK_SESSION);
  const [config, setConfig] = useState(FALLBACK_CONFIG);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    const results = await Promise.allSettled([
      api.get('/api/session/me'),
      api.get('/api/config'),
    ]);

    const [me, cfg] = results;

    if (me.status === 'fulfilled' && me.value) {
      setSession(me.value);
    } else {
      if (me.status === 'rejected') {
        console.warn('[session] /api/session/me failed, falling back to anon:', me.reason?.code || me.reason);
      }
      setSession(FALLBACK_SESSION);
    }

    if (cfg.status === 'fulfilled' && cfg.value) {
      setConfig(cfg.value);
    } else {
      if (cfg.status === 'rejected') {
        console.warn('[session] /api/config failed, using fallback:', cfg.reason?.code || cfg.reason);
      }
      setConfig(FALLBACK_CONFIG);
    }

    setError(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refresh();
      } catch (e) {
        if (!cancelled) setError(e);
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => { cancelled = true; };
  }, [refresh]);

  const initDemo = useCallback(async () => {
    try {
      const r = await api.post('/api/session/init');
      if (r) setSession({ kind: 'demo', ...r });
      return r;
    } catch (e) {
      console.warn('[session] initDemo failed:', e.code, e.message);
      throw e;
    }
  }, []);

  const login = useCallback(async (email, password) => {
    const r = await api.post('/api/auth/login', { email, password });
    await refresh();
    return r;
  }, [refresh]);

  const logout = useCallback(async () => {
    try { await api.post('/api/auth/logout'); } catch (_) { /* no-op */ }
    await refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ session, config, ready, error, refresh, initDemo, login, logout }),
    [session, config, ready, error, refresh, initDemo, login, logout],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSessionContext() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSessionContext must be used inside <SessionProvider>');
  return ctx;
}

// Thin convenience hooks so components don't pull the whole context.
export function useSession() {
  const { session, ready, refresh, initDemo, login, logout } = useSessionContext();
  return { session, ready, refresh, initDemo, login, logout };
}

export function useConfig() {
  const { config, ready } = useSessionContext();
  return { config, ready };
}
