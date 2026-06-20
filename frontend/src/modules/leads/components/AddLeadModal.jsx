import React, { useState } from 'react';
import { SBButton, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../lib/toast.jsx';

// "Add lead" modal. Posts CreateLeadRequest; handles 409 conflict with
// a "view existing" link per the contract.

const INPUT_STYLE = {
  width: '100%',
  padding: '9px 12px',
  background: 'var(--sb-panel)',
  border: '1px solid var(--sb-line-2)',
  color: 'var(--sb-fg)',
  fontSize: 13,
  fontFamily: 'var(--sb-font)',
  outline: 'none',
};

const LABEL_STYLE = { marginBottom: 6, display: 'block' };

const SOURCES = [
  'manual', 'lara', 'hubspot', 'zoho', 'sheets', 'tally',
  'scraper_producthunt', 'scraper_directory', 'scraper_review', 'scraper_linkedin',
];

export default function AddLeadModal({ onClose, onCreated, onViewExisting }) {
  const [form, setForm] = useState({
    name: '', email: '', phone: '', company: '', company_domain: '',
    title: '', source: 'manual', tags: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [conflict, setConflict] = useState(null); // { existing_lead_id }
  const [error, setError] = useState(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setError('Name is required.');
      return;
    }
    setSubmitting(true);
    setError(null);
    setConflict(null);
    try {
      const body = {
        name: form.name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        company_name: form.company.trim() || null,
        company_domain: form.company_domain.trim() || null,
        title: form.title.trim() || null,
        source: form.source || 'manual',
        tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
      };
      const res = await api.post('/api/leads', body);
      toast.success('Lead created');
      onCreated?.(res.lead || res);
      onClose();
    } catch (err) {
      if (err.status === 409 && err.details?.existing_lead_id) {
        setConflict(err.details);
      } else if (err.code === 'network_unreachable') {
        setError('Backend offline — cannot create leads right now.');
      } else {
        setError(err.message || 'Failed to create lead.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 40 }}
      />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        width: 520, maxWidth: '90vw', maxHeight: '90vh', overflow: 'auto',
        background: 'var(--sb-bg)', border: '1px solid var(--sb-line-2)', zIndex: 45,
      }}>
        <div style={{
          padding: '18px 24px', borderBottom: '1px solid var(--sb-line)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>New lead</div>
            <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', marginTop: 2, fontFamily: 'var(--sb-font-mono)' }}>
              create manually · POST /api/leads
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none',
            color: 'var(--sb-fg-4)', cursor: 'pointer',
          }}>
            <SBIcon name="close" size={16} />
          </button>
        </div>

        <form onSubmit={onSubmit} style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <span className="sb-label" style={LABEL_STYLE}>Name *</span>
            <input value={form.name} onChange={(e) => set('name', e.target.value)}
              style={INPUT_STYLE} autoFocus />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <span className="sb-label" style={LABEL_STYLE}>Email</span>
              <input type="email" value={form.email} onChange={(e) => set('email', e.target.value)}
                style={INPUT_STYLE} />
            </div>
            <div>
              <span className="sb-label" style={LABEL_STYLE}>Phone</span>
              <input value={form.phone} onChange={(e) => set('phone', e.target.value)}
                style={INPUT_STYLE} />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <span className="sb-label" style={LABEL_STYLE}>Company</span>
              <input value={form.company} onChange={(e) => set('company', e.target.value)}
                style={INPUT_STYLE} />
            </div>
            <div>
              <span className="sb-label" style={LABEL_STYLE}>Domain</span>
              <input value={form.company_domain} onChange={(e) => set('company_domain', e.target.value)}
                placeholder="acme.com" style={INPUT_STYLE} />
            </div>
          </div>

          <div>
            <span className="sb-label" style={LABEL_STYLE}>Title</span>
            <input value={form.title} onChange={(e) => set('title', e.target.value)}
              style={INPUT_STYLE} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <span className="sb-label" style={LABEL_STYLE}>Source</span>
              <select value={form.source} onChange={(e) => set('source', e.target.value)}
                style={INPUT_STYLE}>
                {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <span className="sb-label" style={LABEL_STYLE}>Tags (comma sep.)</span>
              <input value={form.tags} onChange={(e) => set('tags', e.target.value)}
                placeholder="hot, fintech" style={INPUT_STYLE} />
            </div>
          </div>

          {conflict && (
            <div style={{
              padding: '10px 12px', border: '1px solid var(--sb-warm)',
              background: 'rgba(255,181,71,0.05)', fontSize: 12.5, color: 'var(--sb-fg-2)',
            }}>
              Duplicate lead detected.{' '}
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  onViewExisting?.(conflict.existing_lead_id);
                  onClose();
                }}
                style={{ color: 'var(--sb-accent)', fontWeight: 600, textDecoration: 'underline' }}
              >
                View existing
              </a>
            </div>
          )}

          {error && (
            <div style={{ fontSize: 12, color: 'var(--sb-hot)', fontFamily: 'var(--sb-font-mono)' }}>
              {error}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
            <SBButton variant="ghost" onClick={onClose} type="button">Cancel</SBButton>
            <SBButton variant="primary" icon="plus" type="submit" disabled={submitting}>
              {submitting ? 'Creating…' : 'Create lead'}
            </SBButton>
          </div>
        </form>
      </div>
    </>
  );
}
