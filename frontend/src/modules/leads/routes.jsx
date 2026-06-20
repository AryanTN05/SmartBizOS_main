import React from 'react';
import { Route, Routes } from 'react-router-dom';
import LeadsList from './pages/LeadsList.jsx';
import Integrations from './pages/Integrations.jsx';
import Scrapers from './pages/Scrapers.jsx';
import ScraperResults from './pages/ScraperResults.jsx';
import Accounts from './pages/Accounts.jsx';
import { ToastHost } from './lib/toast.jsx';

// Routes for the M2 Sales Intelligence module.
//
// Mount point (added by the human in App.jsx):
//   <Route path="leads/*" element={<LeadsRoutes />} />
//
// The Integrations + Scrapers pages are NOT under /admin/leads — they're
// siblings at /admin/integrations and /admin/scrapers. The human can either:
//   (a) mount this same default export at "/" with a top-level Route that
//       catches the three prefixes, or
//   (b) mount `LeadsRoutes` at /admin/leads/* and the two exported subpages
//       directly at their own /admin/integrations and /admin/scrapers routes.
//
// For convenience we also export <IntegrationsPage /> and <ScrapersPage />
// so (b) is a one-liner. Routes below cover case (a) — the internal <Routes>
// renders the right page based on the URL prefix under /admin.
export default function LeadsRoutes() {
  return (
    <>
      <Routes>
        <Route index element={<LeadsList />} />
        <Route path=":id" element={<LeadsList />} />
      </Routes>
      <ToastHost />
    </>
  );
}

// Standalone wrappers for direct mounting under /admin/integrations and
// /admin/scrapers. Each mounts its own <ToastHost /> so toasts work even
// when LeadsRoutes isn't in the tree.
export function IntegrationsPage() {
  return (
    <>
      <Integrations />
      <ToastHost />
    </>
  );
}

export function ScrapersPage() {
  return (
    <>
      <Scrapers />
      <ToastHost />
    </>
  );
}

export function ScraperResultsPage() {
  return (
    <>
      <ScraperResults />
      <ToastHost />
    </>
  );
}

export function AccountsPage() {
  return (
    <>
      <Accounts />
      <ToastHost />
    </>
  );
}
