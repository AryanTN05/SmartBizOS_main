import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';

import { SessionProvider, useSession } from './lib/SessionContext.jsx';
import { LaraUIProvider } from './lib/LaraUIContext.jsx';

import { SBSidebar, SBTopBar } from './components/chrome';
import KeyboardCheatsheet from './components/chrome/KeyboardCheatsheet.jsx';
import { SBButton, SBKbd } from './components/primitives';
import LaraDrawerShell from './components/lara/LaraDrawerShell.jsx';
import LaraHotkey from './components/lara/LaraHotkey.jsx';
import { useLaraUI } from './lib/LaraUIContext.jsx';

import DemoLanding from './pages/DemoLanding.jsx';
import DemoExpired from './pages/DemoExpired.jsx';
import AdminLogin from './pages/AdminLogin.jsx';
import NotFound from './pages/NotFound.jsx';
import Home from './pages/admin/Home.jsx';
const Settings = lazy(() => import('./pages/admin/Settings.jsx'));
const Inbox    = lazy(() => import('./pages/admin/Inbox.jsx'));
const Replies  = lazy(() => import('./pages/admin/Replies.jsx'));

// Lazy-load each module's route tree so the initial bundle stays small.
// Vite produces a separate chunk per dynamic import; named pages within the
// same module share that chunk.
const LaraAdminRoutes  = lazy(() => import('./modules/lara/routes.jsx'));
const DemoLaraPage     = lazy(() => import('./modules/lara/routes.jsx').then((m) => ({ default: m.DemoLaraPage })));
const ConversationsList  = lazy(() => import('./modules/lara/routes.jsx').then((m) => ({ default: m.ConversationsList })));
const ConversationDetail = lazy(() => import('./modules/lara/routes.jsx').then((m) => ({ default: m.ConversationDetail })));
const DocumentsPage      = lazy(() => import('./modules/lara/routes.jsx').then((m) => ({ default: m.DocumentsPage })));
const MemoryPage         = lazy(() => import('./modules/lara/routes.jsx').then((m) => ({ default: m.MemoryPage })));
const LeadsRoutes          = lazy(() => import('./modules/leads/routes.jsx'));
const IntegrationsPage     = lazy(() => import('./modules/leads/routes.jsx').then((m) => ({ default: m.IntegrationsPage })));
const ScrapersPage         = lazy(() => import('./modules/leads/routes.jsx').then((m) => ({ default: m.ScrapersPage })));
const ScraperResultsPage   = lazy(() => import('./modules/leads/routes.jsx').then((m) => ({ default: m.ScraperResultsPage })));
const AccountsPage         = lazy(() => import('./modules/leads/routes.jsx').then((m) => ({ default: m.AccountsPage })));
const AutomationsRoutes  = lazy(() => import('./modules/automations/routes.jsx'));
const ReportsRoutes      = lazy(() => import('./modules/reports/routes.jsx'));

// Light placeholder shown while a module chunk is downloading. Avoids the
// blank-flash on first navigation into a module.
function RouteFallback() {
  return (
    <div style={{
      padding: '40px 32px', color: 'var(--sb-fg-5)',
      fontFamily: 'var(--sb-font-mono)', fontSize: 12,
    }}>▸ loading…</div>
  );
}

// Warm every module chunk in the background after the app boots, so the
// first click on any sidebar link feels instant. Uses requestIdleCallback
// when available so it doesn't compete with first paint.
function preloadModules() {
  const tasks = [
    () => import('./modules/lara/routes.jsx'),
    () => import('./modules/leads/routes.jsx'),
    () => import('./modules/automations/routes.jsx'),
    () => import('./modules/reports/routes.jsx'),
  ];
  const run = (fn) => fn().catch(() => { /* preload best-effort */ });
  if (typeof window !== 'undefined') {
    const schedule = window.requestIdleCallback || ((cb) => setTimeout(cb, 1500));
    schedule(() => tasks.forEach(run));
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Top-level app.
// Providers wrap Routes so every page has session + Lara UI state.
// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  // Kick off background preloads on mount so navigation between modules
  // feels instant after the first load.
  React.useEffect(() => { preloadModules(); }, []);

  return (
    <BrowserRouter>
      <SessionProvider>
        <LaraUIProvider>
          <Routes>
            <Route path="/" element={<DemoLanding />} />
            <Route path="/expired" element={<DemoExpired />} />
            <Route path="/admin/login" element={<AdminLogin />} />

            {/* Demo-accessible Lara page. Mounts drawer + hotkey itself. */}
            <Route
              path="/lara"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <LaraHotkey />
                  <DemoLaraPage />
                  <LaraDrawerShell />
                </Suspense>
              }
            />

            {/* Admin shell — all /admin/* routes share sidebar + topbar + drawer. */}
            <Route path="/admin" element={<AdminShell />}>
              <Route index element={<Home />} />
              <Route path="lara/*"           element={<LaraAdminRoutes />} />
              <Route path="conversations"      element={<ConversationsList />} />
              <Route path="conversations/:id"  element={<ConversationDetail />} />
              <Route path="documents"          element={<DocumentsPage />} />
              <Route path="memory"             element={<MemoryPage />} />
              <Route path="leads/*"         element={<LeadsRoutes />} />
              <Route path="accounts"        element={<AccountsPage />} />
              <Route path="integrations"    element={<IntegrationsPage />} />
              <Route path="scrapers"         element={<ScrapersPage />} />
              <Route path="scrapers/results" element={<ScraperResultsPage />} />
              <Route path="automations/*"   element={<AutomationsRoutes />} />
              <Route path="reports/*"       element={<ReportsRoutes />} />
              <Route path="inbox"           element={<Inbox />} />
              <Route path="replies"         element={<Replies />} />
              <Route path="settings"        element={<Settings />} />
            </Route>

            <Route path="*" element={<NotFound />} />
          </Routes>
        </LaraUIProvider>
      </SessionProvider>
    </BrowserRouter>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// AdminShell — requires admin session. If not admin, bounce to /admin/login.
// Provides global chrome and mounts the Lara drawer shell + ⌘J hotkey.
// ─────────────────────────────────────────────────────────────────────────────
function AdminShell() {
  const { session, ready } = useSession();
  const location = useLocation();
  const { openDrawer } = useLaraUI();

  if (!ready) {
    return <BootScreen />;
  }
  if (session?.kind !== 'admin') {
    return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />;
  }

  const crumb = crumbFor(location.pathname);

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <LaraHotkey />
      <SBSidebar />
      <main style={{ flex: 1, minWidth: 0 }}>
        <SBTopBar title={crumb.title} crumb={crumb.trail}>
          <SBButton variant="secondary" size="sm" icon="lara" onClick={() => openDrawer()}>
            Ask Lara <SBKbd>⌘J</SBKbd>
          </SBButton>
        </SBTopBar>
        <Suspense fallback={<RouteFallback />}>
          <Outlet />
        </Suspense>
      </main>
      <LaraDrawerShell />
      <KeyboardCheatsheet />
    </div>
  );
}

function crumbFor(pathname) {
  const map = [
    ['/admin/lara',        { title: 'Lara',       trail: ['SmartBiz OS', 'Lara'] }],
    ['/admin/conversations', { title: 'Conversations',trail: ['SmartBiz OS', 'Lara · History'] }],
    ['/admin/documents',     { title: 'Documents',    trail: ['SmartBiz OS', 'Lara · Knowledge'] }],
    ['/admin/memory',        { title: 'Memory',       trail: ['SmartBiz OS', 'Lara · Memory'] }],
    ['/admin/leads',         { title: 'Leads',        trail: ['SmartBiz OS', 'Sales Intelligence'] }],
    ['/admin/accounts',       { title: 'Accounts',     trail: ['SmartBiz OS', 'Accounts'] }],
    ['/admin/integrations',  { title: 'Integrations', trail: ['SmartBiz OS', 'Integrations'] }],
    ['/admin/scrapers/results', { title: 'Scraper captures', trail: ['SmartBiz OS', 'Scrapers'] }],
    ['/admin/scrapers',      { title: 'Scrapers',     trail: ['SmartBiz OS', 'Scrapers'] }],
    ['/admin/automations',   { title: 'Automation',   trail: ['SmartBiz OS', 'Workflows'] }],
    ['/admin/reports',       { title: 'Reports',      trail: ['SmartBiz OS', 'Reports'] }],
    ['/admin/inbox',         { title: 'Inbox',        trail: ['SmartBiz OS', 'Triage'] }],
    ['/admin/replies',       { title: 'Replies',      trail: ['SmartBiz OS', 'Email replies'] }],
    ['/admin/settings',      { title: 'Settings',     trail: ['SmartBiz OS', 'Workspace'] }],
  ];
  for (const [prefix, data] of map) {
    if (pathname === prefix || pathname.startsWith(prefix + '/')) return data;
  }
  return { title: 'Home', trail: ['SmartBiz OS'] };
}

function BootScreen() {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)', fontSize: 12,
      letterSpacing: '0.12em', textTransform: 'uppercase',
    }}>
      ▸ booting…
    </div>
  );
}
