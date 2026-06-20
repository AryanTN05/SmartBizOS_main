// SmartBiz OS — tiny fetch wrapper.
// Matches the Foundation error envelope: { error: { code, message, details } }.
// - In dev, BASE is empty (Vite proxies /api → backend on 8000).
// - In prod, set VITE_API_BASE_URL if the frontend serves from a different origin.
// - Every request includes credentials so cookies (demo_session / admin_session) ride along.

const BASE = (import.meta.env && import.meta.env.VITE_API_BASE_URL) || '';

export class ApiError extends Error {
  constructor({ code, message, details, status }) {
    super(message || code || 'Request failed');
    this.name = 'ApiError';
    this.code = code || 'unknown';
    this.details = details || null;
    this.status = status;
  }
}

async function request(method, path, body, opts = {}) {
  const isForm = body instanceof FormData;
  const headers = { Accept: 'application/json', ...(opts.headers || {}) };
  let payload;

  if (body !== undefined && body !== null) {
    if (isForm) {
      payload = body;
    } else {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
      payload = JSON.stringify(body);
    }
  }

  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: payload,
      credentials: 'include',
      signal: opts.signal,
    });
  } catch (e) {
    throw new ApiError({
      code: 'network_unreachable',
      message: e.message || 'Network error',
      status: 0,
    });
  }

  if (res.status === 204) return null;

  const ct = res.headers.get('content-type') || '';
  const isJson = ct.includes('application/json');
  const data = isJson ? await res.json().catch(() => null) : await res.text().catch(() => null);

  if (!res.ok) {
    const env = (isJson && data && data.error) || {};
    throw new ApiError({
      code: env.code || `http_${res.status}`,
      message: env.message || res.statusText || 'Request failed',
      details: env.details || null,
      status: res.status,
    });
  }

  return data;
}

// ─── Stale-while-revalidate cache for GETs ──────────────────────────────────
//
// Each entry: { value, expiresAt, inflight: Promise|null }.
// On `get(path)`:
//   - If a fresh value exists, return it (no network).
//   - If a stale value exists, return it AND fire a background refresh.
//   - If no value, await the network.
// Mutations (post/patch/put/delete) clear matching keys so subsequent
// reads see fresh data.

const CACHE = new Map();
const DEFAULT_TTL_MS = 30_000;

function cacheKey(method, path) { return `${method} ${path}`; }

function setCache(path, value, ttlMs = DEFAULT_TTL_MS) {
  CACHE.set(cacheKey('GET', path), {
    value,
    expiresAt: Date.now() + ttlMs,
    inflight: null,
  });
}

function invalidatePrefix(prefix) {
  for (const k of CACHE.keys()) {
    if (k.startsWith('GET ' + prefix)) CACHE.delete(k);
  }
}

// Heuristic: a write to /api/foo/123 invalidates anything starting with /api/foo.
function invalidateForWrite(path) {
  // Strip query, take everything up to and including the resource segment.
  const cleanPath = path.split('?')[0];
  const parts = cleanPath.split('/').filter(Boolean);
  // /api/leads/abc/activity → invalidate /api/leads
  // /api/automations/runs/xyz/pause → invalidate /api/automations/runs
  if (parts.length >= 2) {
    invalidatePrefix('/' + parts.slice(0, 2).join('/'));
    if (parts.length >= 3 && !looksLikeId(parts[2])) {
      invalidatePrefix('/' + parts.slice(0, 3).join('/'));
    }
  }
}

function looksLikeId(s) {
  // UUID, hex, or numeric.
  return /^[0-9a-f]{8,}|^\d+$/i.test(s);
}

async function cachedGet(path, opts = {}) {
  // Bypass cache when caller passes { fresh: true } or sends an AbortSignal
  // (signal-driven calls are usually polling and want fresh data each tick).
  if (opts.fresh || opts.signal) {
    const v = await request('GET', path, undefined, opts);
    setCache(path, v, opts.ttlMs ?? DEFAULT_TTL_MS);
    return v;
  }

  const key = cacheKey('GET', path);
  const entry = CACHE.get(key);
  const now = Date.now();

  if (entry && entry.expiresAt > now && entry.value !== undefined) {
    return entry.value;  // fresh hit
  }

  if (entry && entry.value !== undefined) {
    // Stale-while-revalidate: serve cached value, refresh in background.
    if (!entry.inflight) {
      entry.inflight = request('GET', path, undefined, opts)
        .then((v) => { setCache(path, v, opts.ttlMs ?? DEFAULT_TTL_MS); return v; })
        .catch(() => {})
        .finally(() => { entry.inflight = null; });
    }
    return entry.value;
  }

  // Coalesce concurrent first-time fetches: if there's an in-flight request
  // for this URL but no cached value yet, wait on it instead of firing again.
  if (entry && entry.inflight) {
    return entry.inflight;
  }

  // First-time fetch — must await.
  const inflight = request('GET', path, undefined, opts);
  CACHE.set(key, { value: undefined, expiresAt: 0, inflight });
  try {
    const v = await inflight;
    setCache(path, v, opts.ttlMs ?? DEFAULT_TTL_MS);
    return v;
  } catch (e) {
    CACHE.delete(key);
    throw e;
  }
}

export const api = {
  get: cachedGet,
  post:   (path, body, opts) => request('POST',   path, body, opts).then((r) => { invalidateForWrite(path); return r; }),
  patch:  (path, body, opts) => request('PATCH',  path, body, opts).then((r) => { invalidateForWrite(path); return r; }),
  put:    (path, body, opts) => request('PUT',    path, body, opts).then((r) => { invalidateForWrite(path); return r; }),
  delete: (path, body, opts) => request('DELETE', path, body, opts).then((r) => { invalidateForWrite(path); return r; }),

  // Manually invalidate (e.g., when polling external state).
  invalidate: invalidatePrefix,

  // For SSE: returns the raw Response so the caller can read `.body` as a stream.
  stream: (path, body, opts = {}) => fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: 'include',
    signal: opts.signal,
  }),
};

export default api;
