import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import SBIcon from '../primitives/SBIcon.jsx';
import SBAvatar from '../primitives/SBAvatar.jsx';
import { useConfig, useSession } from '../../lib/SessionContext.jsx';
import { useLaraUI } from '../../lib/LaraUIContext.jsx';

// Nav items. `kind: "route"` items navigate via React Router.
// `kind: "drawer"` items open the Lara drawer (no route change).
// Top-level navigation. Integrations is intentionally absent — it's a
// roadmap-only surface today (no real OAuth adapters yet) and putting it in
// the nav makes users feel deceived when they click expecting to connect a
// CRM. The route still works for deep-links from elsewhere.
const BASE_ITEMS = [
  { key: 'lara',   label: 'Lara',        icon: 'lara',   hint: 'Ask anything',        kind: 'drawer' },
  { key: 'history',  label: 'Conversations', icon: 'clock',    hint: 'Past Lara chats',   kind: 'route', to: '/admin/conversations' },
  { key: 'inbox',    label: 'Inbox',         icon: 'flame',    hint: 'Triage queue',        kind: 'route', to: '/admin/inbox' },
  { key: 'replies',  label: 'Replies',       icon: 'mail',     hint: 'Inbound email replies', kind: 'route', to: '/admin/replies' },
  { key: 'leads',    label: 'Leads',         icon: 'leads',    hint: 'Sales intelligence',  kind: 'route', to: '/admin/leads' },
  { key: 'accts',    label: 'Accounts',      icon: 'building', hint: 'Grouped by company',  kind: 'route', to: '/admin/accounts' },
  { key: 'flow',     label: 'Automation',    icon: 'flow',     hint: 'Sequences + workflows', kind: 'route', to: '/admin/automations' },
  { key: 'reports',  label: 'Reports',       icon: 'reports',  hint: 'Weekly summaries',    kind: 'route', to: '/admin/reports' },
  { key: 'docs',     label: 'Docs',          icon: 'docs',     hint: 'RAG store',           kind: 'route', to: '/admin/documents' },
  { key: 'memory',   label: 'Memory',        icon: 'star',     hint: 'Long-term facts',     kind: 'route', to: '/admin/memory' },
  { key: 'scrape',   label: 'Scrapers',      icon: 'eye',      hint: 'Lead pipelines',      kind: 'route', to: '/admin/scrapers' },
  { key: 'settings', label: 'Settings',      icon: 'settings', hint: 'Workspace + ICP',     kind: 'route', to: '/admin/settings' },
];

const COLLAPSED_W = 72;
const EXPANDED_W = 220;
const STORAGE_KEY = 'sb_sidebar_expanded';

export default function SBSidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { openDrawer } = useLaraUI();
  const { session, logout } = useSession();
  const [expanded, setExpanded] = useState(() => {
    try { return window.localStorage.getItem(STORAGE_KEY) === '1'; }
    catch { return false; }
  });
  const [profileOpen, setProfileOpen] = useState(false);

  useEffect(() => {
    try { window.localStorage.setItem(STORAGE_KEY, expanded ? '1' : '0'); } catch {}
  }, [expanded]);

  const items = BASE_ITEMS;
  const activeKey = items.find((m) => m.kind === 'route' && location.pathname.startsWith(m.to))?.key;

  const demo = session?.kind === 'demo';
  const adminName  = session?.kind === 'admin' ? (session.admin?.name  || 'Admin') : 'Guest';
  const adminEmail = session?.kind === 'admin' ? (session.admin?.email || '') : '';

  const onLogout = async () => {
    setProfileOpen(false);
    try { await logout(); } catch {}
    navigate('/admin/login');
  };

  return (
    <aside style={{
      width: expanded ? EXPANDED_W : COLLAPSED_W,
      borderRight: '1px solid var(--sb-line)',
      background: 'var(--sb-bg-2)', display: 'flex', flexDirection: 'column',
      alignItems: expanded ? 'stretch' : 'center',
      padding: expanded ? '16px 12px 14px' : '16px 0 14px',
      position: 'sticky', top: 0, height: '100vh', flexShrink: 0,
      transition: 'width 180ms cubic-bezier(.2,.8,.2,1)',
    }}>
      {/* Logo + collapse toggle */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        marginBottom: 24,
        justifyContent: expanded ? 'space-between' : 'center',
      }}>
        <button
          onClick={() => navigate('/admin')}
          style={{
            width: 40, height: 40, background: 'var(--sb-accent)', color: '#000',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--sb-font-display)', fontSize: 22, fontWeight: 700,
            letterSpacing: '-0.04em', cursor: 'pointer', border: 0, flexShrink: 0,
          }}
        >sb</button>
        {expanded && (
          <button
            onClick={() => setExpanded(false)}
            title="Collapse sidebar"
            style={{
              background: 'transparent', border: 'none',
              color: 'var(--sb-fg-5)', cursor: 'pointer', padding: 6,
              display: 'flex', alignItems: 'center',
            }}
          >
            <SBIcon name="chevronL" size={16} />
          </button>
        )}
      </div>

      <nav style={{
        flex: 1, display: 'flex', flexDirection: 'column', gap: 2,
        width: '100%', alignItems: expanded ? 'stretch' : 'center',
      }}>
        {items.map((m) => (
          <NavBtn
            key={m.key}
            item={m}
            active={activeKey === m.key}
            expanded={expanded}
            onClick={() => (m.kind === 'drawer' ? openDrawer() : navigate(m.to))}
          />
        ))}
      </nav>

      {/* Expand toggle (collapsed only — when expanded the chevron up top handles it) */}
      {!expanded && (
        <button
          onClick={() => setExpanded(true)}
          title="Expand sidebar"
          style={{
            background: 'transparent', border: 'none',
            color: 'var(--sb-fg-5)', cursor: 'pointer',
            width: 32, height: 32, marginBottom: 8,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <SBIcon name="chevronR" size={14} />
        </button>
      )}

      {/* Profile area */}
      <div style={{
        display: 'flex',
        flexDirection: expanded ? 'column' : 'column',
        alignItems: 'center', gap: 10,
        paddingTop: 12, width: '100%', borderTop: '1px solid var(--sb-line)',
        position: 'relative',
      }}>
        {demo && !expanded && (
          <div style={{
            writingMode: 'vertical-rl', transform: 'rotate(180deg)',
            fontSize: 9, letterSpacing: '0.24em', textTransform: 'uppercase',
            color: 'var(--sb-accent)', fontFamily: 'var(--sb-font-mono)', fontWeight: 600,
            padding: '4px 0',
          }}>DEMO</div>
        )}

        <ProfileButton
          expanded={expanded}
          name={adminName}
          email={adminEmail}
          demo={demo}
          open={profileOpen}
          onToggle={() => setProfileOpen((v) => !v)}
        />

        {profileOpen && (
          <ProfileMenu
            expanded={expanded}
            name={adminName}
            email={adminEmail}
            demo={demo}
            onClose={() => setProfileOpen(false)}
            onSettings={() => { setProfileOpen(false); navigate('/admin/settings'); }}
            onLogout={onLogout}
          />
        )}
      </div>
    </aside>
  );
}

function NavBtn({ item, active, expanded, onClick }) {
  const [hover, setHover] = useState(false);
  return (
    <div
      style={{
        position: 'relative', width: '100%',
        display: 'flex',
        justifyContent: expanded ? 'flex-start' : 'center',
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <button
        onClick={onClick}
        style={{
          width: expanded ? '100%' : 44, height: 40,
          background: active ? 'var(--sb-accent-bg)' : (hover ? 'var(--sb-card)' : 'transparent'),
          color: active ? 'var(--sb-accent)' : hover ? 'var(--sb-fg)' : 'var(--sb-fg-3)',
          border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 12,
          padding: expanded ? '0 12px' : 0,
          justifyContent: expanded ? 'flex-start' : 'center',
          position: 'relative', transition: 'all 140ms',
          fontFamily: 'var(--sb-font)', fontSize: 13,
          textAlign: 'left',
        }}
      >
        <SBIcon name={item.icon} size={18} stroke={1.4} />
        {expanded && <span style={{ flex: 1, fontWeight: active ? 600 : 500 }}>{item.label}</span>}
        {active && (
          <div style={{ position: 'absolute', left: 0, top: 8, bottom: 8, width: 2, background: 'var(--sb-accent)' }} />
        )}
      </button>
      {hover && !expanded && (
        <div style={{
          position: 'absolute', left: 56, top: '50%', transform: 'translateY(-50%)',
          background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-2)',
          padding: '6px 10px', fontSize: 11.5, whiteSpace: 'nowrap', zIndex: 100,
          pointerEvents: 'none', display: 'flex', flexDirection: 'column', gap: 2,
        }}>
          <div style={{ color: 'var(--sb-fg)', fontWeight: 600 }}>{item.label}</div>
          <div style={{ color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', fontSize: 10 }}>{item.hint}</div>
        </div>
      )}
    </div>
  );
}

function ProfileButton({ expanded, name, email, demo, open, onToggle }) {
  if (!expanded) {
    return (
      <button
        onClick={onToggle}
        title={`${name}${email ? ` · ${email}` : ''}`}
        style={{
          background: open ? 'var(--sb-card)' : 'transparent', border: 'none', cursor: 'pointer',
          padding: 4, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <SBAvatar name={name} color="var(--sb-accent)" size={32} />
      </button>
    );
  }
  return (
    <button
      onClick={onToggle}
      style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
        background: open ? 'var(--sb-card)' : 'transparent', border: '1px solid var(--sb-line)',
        padding: '8px 10px', cursor: 'pointer', textAlign: 'left',
      }}
    >
      <SBAvatar name={name} color="var(--sb-accent)" size={28} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--sb-fg)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {name}
        </div>
        {email && (
          <div style={{ fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {email}
          </div>
        )}
        {demo && (
          <div style={{ fontSize: 9, color: 'var(--sb-accent)', fontFamily: 'var(--sb-font-mono)', textTransform: 'uppercase', letterSpacing: '0.12em', marginTop: 2 }}>
            demo
          </div>
        )}
      </div>
      <SBIcon name={open ? 'chevronD' : 'chevronR'} size={12} stroke={1.5} />
    </button>
  );
}

function ProfileMenu({ expanded, name, email, demo, onClose, onSettings, onLogout }) {
  // Click-outside to close.
  const ref = useRef(null);
  useEffect(() => {
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    // setTimeout so the same click that opened the menu doesn't immediately close it.
    const t = setTimeout(() => document.addEventListener('mousedown', onDoc), 0);
    return () => { clearTimeout(t); document.removeEventListener('mousedown', onDoc); };
  }, [onClose]);

  return (
    <div
      ref={ref}
      style={{
        position: 'absolute',
        bottom: '100%', marginBottom: 8,
        left: expanded ? 0 : 56,
        right: expanded ? 0 : 'auto',
        minWidth: expanded ? undefined : 200,
        background: 'var(--sb-card-2)', border: '1px solid var(--sb-line-2)',
        zIndex: 110, padding: 4,
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }}
    >
      <div style={{
        padding: '10px 12px', borderBottom: '1px solid var(--sb-line)',
        marginBottom: 4,
      }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--sb-fg)' }}>{name}</div>
        {email && (
          <div style={{ fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', marginTop: 2 }}>
            {email}
          </div>
        )}
        {demo && (
          <div style={{ fontSize: 9, color: 'var(--sb-accent)', fontFamily: 'var(--sb-font-mono)', textTransform: 'uppercase', letterSpacing: '0.12em', marginTop: 4 }}>
            demo session
          </div>
        )}
      </div>
      <MenuItem icon="settings" label="Workspace settings" onClick={onSettings} />
      <MenuItem icon="close" label="Log out" onClick={onLogout} tone="hot" />
    </div>
  );
}

function MenuItem({ icon, label, onClick, tone }) {
  const [hover, setHover] = useState(false);
  const fg = tone === 'hot' ? 'var(--sb-hot)' : 'var(--sb-fg)';
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 10px', background: hover ? 'var(--sb-panel)' : 'transparent',
        border: 'none', color: fg, cursor: 'pointer',
        fontSize: 12.5, fontFamily: 'var(--sb-font)', textAlign: 'left',
      }}
    >
      <SBIcon name={icon} size={14} stroke={1.5} />
      <span>{label}</span>
    </button>
  );
}
