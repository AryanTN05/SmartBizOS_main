// Tiny toast system — no external dep. Imperative API: toast.push('msg', 'error').
// The <ToastHost /> component reads from a module-scoped subscribe/emit.

import React, { useEffect, useState } from 'react';

let listeners = [];
let nextId = 1;

function emit(list) {
  listeners.forEach((l) => l(list));
}

const toasts = [];

function dismissToast(id) {
  const idx = toasts.findIndex((t) => t.id === id);
  if (idx >= 0) {
    toasts.splice(idx, 1);
    emit([...toasts]);
  }
}

export const toast = {
  // `opts` may include { duration, action: { label, onClick } } for undo
  // toasts. Default duration stays 4200ms for normal toasts; undo flows
  // pass 6000+ so the user has time to react.
  push(message, tone = 'info', opts = {}) {
    const id = nextId++;
    const entry = {
      id, message, tone,
      action: opts.action || null,
      // Pass dismiss to action handler so onClick can clear the toast.
      _dismiss: () => dismissToast(id),
    };
    toasts.push(entry);
    emit([...toasts]);
    setTimeout(() => dismissToast(id), opts.duration || 4200);
    return id;
  },
  error(message, opts) { return toast.push(message, 'error', opts); },
  success(message, opts) { return toast.push(message, 'success', opts); },
  info(message, opts) { return toast.push(message, 'info', opts); },
  dismiss(id) { dismissToast(id); },
};

export function ToastHost() {
  const [list, setList] = useState(toasts);
  useEffect(() => {
    const fn = (next) => setList(next);
    listeners.push(fn);
    return () => { listeners = listeners.filter((l) => l !== fn); };
  }, []);

  const colors = {
    info: { bg: 'var(--sb-card-2)', fg: 'var(--sb-fg)', border: 'var(--sb-line-2)' },
    error: { bg: 'var(--sb-card-2)', fg: 'var(--sb-hot)', border: 'var(--sb-hot)' },
    success: { bg: 'var(--sb-card-2)', fg: 'var(--sb-accent)', border: 'var(--sb-accent)' },
  };

  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, zIndex: 80,
      display: 'flex', flexDirection: 'column', gap: 8, pointerEvents: 'none',
    }}>
      {list.map((t) => {
        const c = colors[t.tone] || colors.info;
        return (
          <div key={t.id} style={{
            background: c.bg, color: c.fg, border: `1px solid ${c.border}`,
            padding: '10px 14px', fontSize: 12.5, fontFamily: 'var(--sb-font-mono)',
            minWidth: 220, maxWidth: 460, pointerEvents: 'auto',
            display: 'flex', alignItems: 'center', gap: 12,
            animation: 'sb-toast-in 160ms ease-out',
          }}>
            <span style={{ flex: 1 }}>{t.message}</span>
            {t.action && (
              <button
                onClick={() => { t.action.onClick?.(); t._dismiss(); }}
                style={{
                  background: 'transparent', border: `1px solid ${c.border}`,
                  color: c.fg, cursor: 'pointer',
                  padding: '4px 10px', fontSize: 11, fontFamily: 'var(--sb-font-mono)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                }}
              >{t.action.label}</button>
            )}
          </div>
        );
      })}
      <style>{`
        @keyframes sb-toast-in {
          from { opacity: 0; transform: translateX(12px); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}
