import React, { useEffect, useState } from 'react';

// Global keyboard cheatsheet. Press `?` anywhere to open. Esc to close.
// Mounted once at the AdminShell level so every route has it.
//
// Shortcuts are grouped by surface so the SDR sees only what's relevant
// at the moment they're stuck and reaching for `?`.

const SECTIONS = [
  {
    title: 'Global',
    items: [
      ['?',         'Open this cheatsheet'],
      ['⌘ J / Ctrl J', 'Toggle Lara drawer'],
      ['G then I',  'Go to Inbox'],
      ['G then L',  'Go to Leads'],
      ['G then A',  'Go to Accounts'],
      ['G then R',  'Go to Reports'],
    ],
  },
  {
    title: 'Inbox · Triage',
    items: [
      ['↑ / ↓',     'Move focus between captures'],
      ['J / K',     'Same as ↓ / ↑'],
      ['Space',     'Expand the focused row'],
      ['C',         'Convert focused capture to a lead'],
      ['V',         'Convert + start a sequence'],
      ['X',         'Dismiss focused capture'],
      ['E',         'Re-enrich focused capture'],
    ],
  },
  {
    title: 'Lead drawer',
    items: [
      ['Esc',       'Close drawer / modal'],
      ['Enter',     'Save inline-edited field'],
      ['⌘ Enter',   'Send compose / mark replied'],
    ],
  },
];


export default function KeyboardCheatsheet() {
  const [open, setOpen] = useState(false);
  const [gPending, setGPending] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      // Don't intercept while typing into inputs / textareas / editable elements.
      const tag = (e.target?.tagName || '').toLowerCase();
      const editable = e.target?.isContentEditable;
      if (tag === 'input' || tag === 'textarea' || editable) return;

      if (e.key === '?' && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setOpen((v) => !v);
        return;
      }
      if (open && e.key === 'Escape') {
        setOpen(false);
        return;
      }
      // Global "g then X" navigation. Set a 600ms pending state, then
      // the next key navigates.
      if (e.key === 'g' && !e.metaKey && !e.ctrlKey && !gPending) {
        setGPending(true);
        setTimeout(() => setGPending(false), 700);
        return;
      }
      if (gPending) {
        const map = { i: '/admin/inbox', l: '/admin/leads',
                      a: '/admin/accounts', r: '/admin/reports' };
        const target = map[e.key.toLowerCase()];
        if (target) {
          e.preventDefault();
          window.location.assign(target);
        }
        setGPending(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, gPending]);

  if (!open) return null;
  return (
    <div onClick={() => setOpen(false)} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 60,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-2)',
        width: 560, maxWidth: '94%', maxHeight: '88vh', overflow: 'auto',
        padding: 24,
      }}>
        <div style={{
          display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14,
        }}>
          <h2 style={{ fontSize: 18, margin: 0, fontWeight: 600 }}>Keyboard shortcuts</h2>
          <span style={{ fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)' }}>
            press ? again or Esc to close
          </span>
        </div>
        {SECTIONS.map((section) => (
          <div key={section.title} style={{ marginBottom: 18 }}>
            <div className="sb-label" style={{ marginBottom: 8 }}>{section.title}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {section.items.map(([key, desc]) => (
                <div key={key} style={{
                  display: 'grid', gridTemplateColumns: '140px 1fr', gap: 12,
                  fontSize: 12.5, alignItems: 'baseline',
                }}>
                  <span style={{
                    fontFamily: 'var(--sb-font-mono)',
                    color: 'var(--sb-accent)', fontSize: 11,
                  }}>{key}</span>
                  <span style={{ color: 'var(--sb-fg-2)' }}>{desc}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
        <div style={{
          fontSize: 11, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
          paddingTop: 12, borderTop: '1px solid var(--sb-line)',
        }}>
          ▸ shortcuts work everywhere except inside text fields
        </div>
      </div>
    </div>
  );
}
