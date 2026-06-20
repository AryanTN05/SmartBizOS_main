import React, { useCallback, useEffect, useRef, useState } from 'react';
import { SBButton, SBChip, SBIcon } from '../../../components/primitives';
import api, { ApiError } from '../../../lib/api.js';
import EmptyState from '../components/EmptyState.jsx';

// Documents admin page:
//   - Upload zone (drag + click). POST /api/documents/upload (multipart).
//   - List (GET /api/documents).
//   - For pending docs, poll /api/documents/:id every 2s until ready or failed.
//   - Delete button per row.
//
// Error handling per the foundation envelope:
//   413 → "File too large (max 20 MB)"
//   402 + details.reason === "doc_limit" → "Demo users can upload 1 doc per session."
export default function DocumentsPage() {
  const [state, setState] = useState({ status: 'loading', items: [] });
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const inputRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/api/documents?limit=50');
      setState({ status: 'ok', items: r?.items || [] });
    } catch (_) {
      setState({ status: 'empty', items: [] });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Extraction is synchronous in the upload handler — it only ever returns
  // 'ready' or 'failed', never 'pending'. The polling that used to live
  // here was speculating an async extraction worker that never materialized.
  // Removed; if we ever queue extraction we'll add it back with a real
  // worker on the other end.

  const onUpload = async (file) => {
    if (!file) return;
    setUploadError(null);
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await api.post('/api/documents/upload', fd);
      if (r?.document) {
        setState((s) => ({ status: 'ok', items: [r.document, ...(s.items || [])] }));
      } else {
        await load();
      }
    } catch (e) {
      setUploadError(mapUploadError(e));
    } finally {
      setUploading(false);
    }
  };

  const onDelete = async (id) => {
    if (!window.confirm('Delete this document?')) return;
    try { await api.delete(`/api/documents/${id}`); } catch (_) { /* no-op */ }
    setState((s) => ({ ...s, items: s.items.filter((d) => d.id !== id) }));
  };

  const onDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer?.files?.[0];
    if (f) onUpload(f);
  };

  return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{ marginBottom: 20 }}>
        <div className="sb-label">M1 · Lara</div>
        <h1 style={{
          fontFamily: 'var(--sb-font-display)', fontSize: 28, fontWeight: 500,
          margin: '6px 0 0', letterSpacing: '-0.02em',
        }}>Documents</h1>
        <p style={{ color: 'var(--sb-fg-3)', fontSize: 13, marginTop: 6 }}>
          Corpus Lara can answer from. PDF, DOCX, TXT, MD · max 20 MB.
        </p>
      </div>

      {/* Upload zone */}
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: '1px dashed var(--sb-line-3)', padding: 28,
          background: 'var(--sb-bg-2)', cursor: 'pointer', textAlign: 'center',
          marginBottom: 20,
        }}
      >
        <input
          ref={inputRef} type="file" hidden
          onChange={(e) => onUpload(e.target.files?.[0])}
        />
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 10,
          color: 'var(--sb-accent)',
        }}>
          <SBIcon name="docs" size={18} stroke={1.5} />
          <span style={{ fontSize: 13.5, fontWeight: 600 }}>
            {uploading ? 'Uploading…' : 'Drop a file, or click to choose'}
          </span>
        </div>
        {uploadError && (
          <div style={{
            marginTop: 10, color: 'var(--sb-hot)', fontSize: 12,
            fontFamily: 'var(--sb-font-mono)',
          }}>{uploadError}</div>
        )}
      </div>

      {/* List */}
      {state.status === 'loading' && (
        <div style={{
          fontFamily: 'var(--sb-font-mono)', fontSize: 12, color: 'var(--sb-fg-5)',
        }}>loading…</div>
      )}
      {state.status === 'empty' && (
        <EmptyState detail="Documents endpoint isn't online yet." />
      )}
      {state.status === 'ok' && state.items.length === 0 && (
        <EmptyState title="No documents yet" detail="Upload a contract, spec, or doc above." />
      )}
      {state.status === 'ok' && state.items.length > 0 && (
        <div style={{ border: '1px solid var(--sb-line)', background: 'var(--sb-card)' }}>
          {state.items.map((d, i) => (
            <div key={d.id} style={{
              display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px',
              borderTop: i > 0 ? '1px solid var(--sb-line)' : 'none',
            }}>
              <SBIcon name="docs" size={18} stroke={1.4} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 13.5, fontWeight: 500, color: 'var(--sb-fg)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>{d.filename}</div>
                <div style={{
                  fontSize: 11, color: 'var(--sb-fg-5)',
                  fontFamily: 'var(--sb-font-mono)', marginTop: 3,
                }}>
                  {fmtBytes(d.size_bytes)} · {d.mime_type || '—'}
                  {d.page_count != null ? ` · ${d.page_count}p` : ''}
                  {d.chunk_count != null ? ` · ${d.chunk_count} chunks` : ''}
                </div>
              </div>
              <StatusChip status={d.extraction_status} error={d.extraction_error} />
              <SBButton variant="ghost" size="xs" onClick={() => onDelete(d.id)}>
                <span style={{ color: 'var(--sb-hot)' }}>Delete</span>
              </SBButton>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusChip({ status, error }) {
  if (status === 'ready')   return <SBChip tone="lime">ready</SBChip>;
  if (status === 'pending') return <SBChip tone="warm">extracting</SBChip>;
  if (status === 'failed')  return <SBChip tone="hot" title={error || ''}>failed</SBChip>;
  return <SBChip tone="muted">{status || 'unknown'}</SBChip>;
}

function fmtBytes(n) {
  if (n == null) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function mapUploadError(e) {
  if (!(e instanceof ApiError)) return e?.message || 'Upload failed.';
  if (e.status === 413) return 'File too large (max 20 MB).';
  if (e.status === 402 && e.details?.reason === 'doc_limit') {
    return 'Demo users can upload 1 doc per session.';
  }
  if (e.status === 422) return e.message || 'Unsupported file type.';
  if (e.code === 'network_unreachable') return 'Backend unreachable — upload endpoint offline.';
  return e.message || 'Upload failed.';
}
