import React, { useState } from 'react';
import { SBButton } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../lib/toast.jsx';

// CSV import — two-step flow (preview, then commit). Backend auto-suggests
// header→field mapping; user confirms / changes via per-field dropdowns.
// Dedupes on tenant + email; duplicates are silently skipped server-side.

const INPUT = {
  width: '100%', padding: '8px 10px',
  background: 'var(--sb-panel)', border: '1px solid var(--sb-line-2)',
  color: 'var(--sb-fg)', fontSize: 13, fontFamily: 'var(--sb-font)', outline: 'none',
};

const FIELD_LABELS = {
  email:          'Email',
  name:           'Full name',
  company_name:   'Company',
  company_domain: 'Company domain',
  title:          'Job title',
  phone:          'Phone',
  linkedin_url:   'LinkedIn URL',
  tags:           'Tags',
};

export default function ImportCsvModal({ onClose, onImported }) {
  const [csvText, setCsvText] = useState('');
  const [filename, setFilename] = useState('');
  const [preview, setPreview] = useState(null); // {headers, row_count, suggested_mapping, preview_rows, supported_fields}
  const [mapping, setMapping] = useState({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // {inserted, skipped_duplicates, skipped_invalid, errors}
  const [error, setError] = useState(null);

  const onFile = async (file) => {
    if (!file) return;
    if (file.size > 1_500_000) {
      setError(`File is ${Math.round(file.size / 1024)}KB — limit is 1.5MB.`);
      return;
    }
    setError(null);
    setFilename(file.name);
    const text = await file.text();
    setCsvText(text);
    await runPreview(text);
  };

  const runPreview = async (text) => {
    if (!text || !text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.post('/api/leads/import-csv/preview', { csv_text: text });
      setPreview(r);
      setMapping(r.suggested_mapping || {});
    } catch (err) {
      setError(err?.message || 'Could not parse CSV.');
      setPreview(null);
    } finally {
      setBusy(false);
    }
  };

  const onCommit = async () => {
    if (!preview) return;
    if (!mapping.name && !mapping.email) {
      setError('Map at least one of Name or Email before importing.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await api.post('/api/leads/import-csv', {
        csv_text: csvText,
        mapping,
        source: 'csv_import',
        tags: [],
      });
      setResult(r);
      onImported?.(r);
      if (r.inserted > 0) {
        toast.success(`Imported ${r.inserted} lead${r.inserted === 1 ? '' : 's'}.`);
      }
    } catch (err) {
      setError(err?.message || 'Import failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div onClick={onClose} style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 30,
      }} />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        background: 'var(--sb-bg)', border: '1px solid var(--sb-line-2)',
        width: 720, maxWidth: '92vw', maxHeight: '88vh', zIndex: 35,
        display: 'flex', flexDirection: 'column',
      }}>
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid var(--sb-line)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>Import leads from CSV</div>
            <div style={{ fontSize: 11.5, color: 'var(--sb-fg-5)', marginTop: 2 }}>
              Header-based mapping. Duplicates (by email) are skipped.
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', color: 'var(--sb-fg-4)',
            cursor: 'pointer', fontSize: 18,
          }}>×</button>
        </div>

        <div style={{ padding: 20, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Result panel — when import is done */}
          {result ? (
            <div style={{
              padding: 18, background: 'var(--sb-card)', border: '1px solid var(--sb-line-2)',
            }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>Import complete</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, fontSize: 12.5 }}>
                <Stat label="inserted" value={result.inserted} tone="var(--sb-accent)" />
                <Stat label="duplicates skipped" value={result.skipped_duplicates} tone="var(--sb-fg-4)" />
                <Stat label="invalid skipped" value={result.skipped_invalid} tone="var(--sb-hot)" />
              </div>
              {(result.errors || []).length > 0 && (
                <div style={{ marginTop: 14, fontSize: 11.5, color: 'var(--sb-fg-4)' }}>
                  <div style={{ fontFamily: 'var(--sb-font-mono)', marginBottom: 4 }}>errors (first 25):</div>
                  {result.errors.slice(0, 25).map((e, i) => (
                    <div key={i} style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11 }}>
                      row {e.row}: {e.reason}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : !preview ? (
            <>
              {/* Step 1 — file picker / paste area */}
              <div>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--sb-fg-4)', marginBottom: 6 }}>
                  Upload a .csv file
                </label>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(e) => onFile(e.target.files?.[0])}
                  style={{ ...INPUT, padding: '7px 8px' }}
                />
                {filename && (
                  <div style={{ fontSize: 11, color: 'var(--sb-fg-5)', marginTop: 4, fontFamily: 'var(--sb-font-mono)' }}>
                    ▸ {filename}
                  </div>
                )}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--sb-fg-5)', textAlign: 'center', marginTop: -4 }}>
                — or paste CSV below —
              </div>
              <textarea
                value={csvText}
                onChange={(e) => setCsvText(e.target.value)}
                placeholder={'name,email,company,title\nKartik,kartik@zerotoprod.com,Zerotoprod,Founder'}
                rows={6}
                style={{ ...INPUT, fontFamily: 'var(--sb-font-mono)', resize: 'vertical' }}
              />
              <SBButton variant="primary" size="sm" disabled={!csvText.trim() || busy}
                onClick={() => runPreview(csvText)}>
                {busy ? 'Parsing…' : 'Preview'}
              </SBButton>
            </>
          ) : (
            <>
              {/* Step 2 — mapping + preview */}
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                  Found {preview.row_count} row{preview.row_count === 1 ? '' : 's'}
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--sb-fg-5)' }}>
                  Headers: <span style={{ fontFamily: 'var(--sb-font-mono)' }}>{preview.headers.join(', ')}</span>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                {Object.entries(FIELD_LABELS).map(([field, label]) => (
                  <div key={field}>
                    <label style={{ display: 'block', fontSize: 11, color: 'var(--sb-fg-5)',
                                    fontFamily: 'var(--sb-font-mono)', marginBottom: 4,
                                    textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                      {label}{(field === 'name' || field === 'email') ? ' *' : ''}
                    </label>
                    <select
                      value={mapping[field] || ''}
                      onChange={(e) => setMapping({ ...mapping, [field]: e.target.value || null })}
                      style={INPUT}
                    >
                      <option value="">— skip —</option>
                      {preview.headers.map((h) => (<option key={h} value={h}>{h}</option>))}
                    </select>
                  </div>
                ))}
              </div>

              {(preview.preview_rows || []).length > 0 && (
                <div style={{
                  background: 'var(--sb-card)', border: '1px solid var(--sb-line)',
                  padding: 12, fontSize: 11.5, fontFamily: 'var(--sb-font-mono)',
                  maxHeight: 160, overflow: 'auto',
                }}>
                  <div style={{ color: 'var(--sb-fg-5)', marginBottom: 6 }}>preview · first 3 rows</div>
                  {preview.preview_rows.slice(0, 3).map((r, i) => (
                    <div key={i} style={{ marginBottom: 4, color: 'var(--sb-fg-2)' }}>
                      {Object.entries(r).slice(0, 4).map(([k, v]) => `${k}=${v}`).join(' · ')}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {error && (
            <div style={{
              padding: '10px 12px', background: 'var(--sb-hot-bg)',
              border: '1px solid var(--sb-hot)', color: 'var(--sb-hot)', fontSize: 12,
            }}>{error}</div>
          )}
        </div>

        <div style={{
          padding: '12px 20px', borderTop: '1px solid var(--sb-line)',
          display: 'flex', gap: 8, justifyContent: 'flex-end',
        }}>
          <SBButton variant="ghost" size="sm" onClick={onClose}>
            {result ? 'Close' : 'Cancel'}
          </SBButton>
          {preview && !result && (
            <SBButton variant="primary" size="sm" icon="check"
              disabled={busy || (!mapping.name && !mapping.email)}
              onClick={onCommit}>
              {busy ? 'Importing…' : `Import ${preview.row_count} rows`}
            </SBButton>
          )}
        </div>
      </div>
    </>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div>
      <div style={{
        fontFamily: 'var(--sb-font-mono)', fontSize: 22, fontWeight: 500, color: tone,
      }}>{value}</div>
      <div style={{
        fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
        textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 2,
      }}>{label}</div>
    </div>
  );
}
