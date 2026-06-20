import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api, ApiError } from './api.js';

describe('api', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('parses a JSON 200 response', async () => {
    fetch.mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200, headers: { 'content-type': 'application/json' },
    }));
    await expect(api.get('/api/health')).resolves.toEqual({ ok: true });
  });

  it('returns null on 204', async () => {
    fetch.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api.delete('/api/x')).resolves.toBeNull();
  });

  it('throws ApiError with envelope code on 4xx', async () => {
    fetch.mockResolvedValue(new Response(
      JSON.stringify({ error: { code: 'not_found', message: 'gone', details: { id: 1 } } }),
      { status: 404, headers: { 'content-type': 'application/json' } },
    ));
    await expect(api.get('/api/x')).rejects.toMatchObject({
      name: 'ApiError', code: 'not_found', status: 404, details: { id: 1 },
    });
  });

  it('normalises network errors into ApiError', async () => {
    fetch.mockRejectedValue(new TypeError('Failed to fetch'));
    let caught;
    try { await api.get('/api/x'); } catch (e) { caught = e; }
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught.code).toBe('network_unreachable');
    expect(caught.status).toBe(0);
  });

  it('falls back to http_<status> when no envelope', async () => {
    fetch.mockResolvedValue(new Response('boom', { status: 500 }));
    await expect(api.get('/api/x')).rejects.toMatchObject({ code: 'http_500' });
  });
});
