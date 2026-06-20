import React from 'react';
import { Link, Route, Routes, useLocation } from 'react-router-dom';

import AutomationView from './pages/AutomationView.jsx';
import Templates from './pages/Templates.jsx';
import TemplateDetail from './pages/TemplateDetail.jsx';
import Channels from './pages/Channels.jsx';

// Sub-nav for the M3 module. Mounted by the human at /admin/automations/*.
// App.jsx currently points /admin/automations/* at ModuleStub — the human
// swaps that route's element for <AutomationsRoutes />.
export default function AutomationsRoutes() {
  return (
    <>
      <SubNav />
      <Routes>
        {/* Runs list + detail. When a run is selected the URL becomes /:run_id */}
        <Route index element={<AutomationView />} />
        <Route path=":run_id" element={<AutomationView />} />

        {/* Templates */}
        <Route path="templates" element={<Templates />} />
        <Route path="templates/:id" element={<TemplateDetail />} />

        {/* Channels registry */}
        <Route path="channels" element={<Channels />} />
      </Routes>
    </>
  );
}

function SubNav() {
  const { pathname } = useLocation();
  const tabs = [
    { to: '/admin/automations', label: 'Runs', match: (p) => p === '/admin/automations' || /^\/admin\/automations\/[^/]+$/.test(p) && !p.startsWith('/admin/automations/templates') && !p.startsWith('/admin/automations/channels') },
    { to: '/admin/automations/templates', label: 'Templates', match: (p) => p.startsWith('/admin/automations/templates') },
    { to: '/admin/automations/channels', label: 'Channels', match: (p) => p.startsWith('/admin/automations/channels') },
  ];
  return (
    <div style={{
      display: 'flex', gap: 0, padding: '0 20px',
      borderBottom: '1px solid var(--sb-line)', background: 'var(--sb-bg)',
    }}>
      {tabs.map((t) => {
        const active = t.match(pathname);
        return (
          <Link
            key={t.to}
            to={t.to}
            style={{
              padding: '12px 16px', textDecoration: 'none',
              fontFamily: 'var(--sb-font-mono)', fontSize: 11,
              letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 600,
              color: active ? 'var(--sb-accent)' : 'var(--sb-fg-4)',
              borderBottom: `2px solid ${active ? 'var(--sb-accent)' : 'transparent'}`,
              marginBottom: -1,
            }}
          >
            {t.label}
          </Link>
        );
      })}
    </div>
  );
}
