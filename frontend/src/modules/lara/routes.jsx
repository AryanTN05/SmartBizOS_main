import React from 'react';
import { Route, Routes } from 'react-router-dom';

import LaraFull from './pages/LaraFull.jsx';
import ConversationsList from './pages/ConversationsList.jsx';
import ConversationDetail from './pages/ConversationDetail.jsx';
import DocumentsPage from './pages/DocumentsPage.jsx';
import MemoryPage from './pages/MemoryPage.jsx';

// ADMIN routes subtree. Mount anywhere under `/admin/*`:
//
//   <Route path="lara/*"        element={<LaraAdminRoutes />} />
//   <Route path="conversations/*" element={<LaraAdminRoutes />} />
//   <Route path="documents/*"     element={<LaraAdminRoutes />} />
//   <Route path="memory/*"        element={<LaraAdminRoutes />} />
//
// …or the simpler option: mount once at the root of the admin tree with
// `<Route path="*" element={<LaraAdminRoutes />} />` — the internal
// <Routes> below handles all four prefixes.
//
// The human wiring this into App.jsx can pick whichever shape fits.
export default function LaraAdminRoutes() {
  return (
    <Routes>
      {/* /admin/lara — full-page admin chat with conversation rail */}
      <Route path="lara/*" element={<LaraFull mode="admin" />} />
      {/* alias: bare "" also renders the admin chat so a parent <Route path="lara/*"> works */}
      <Route index element={<LaraFull mode="admin" />} />

      {/* /admin/conversations */}
      <Route path="conversations" element={<ConversationsList />} />
      <Route path="conversations/:id" element={<ConversationDetail />} />

      {/* /admin/documents */}
      <Route path="documents" element={<DocumentsPage />} />

      {/* /admin/memory */}
      <Route path="memory" element={<MemoryPage />} />
    </Routes>
  );
}

// Demo-facing full-page Lara. Use at the top level (e.g., /lara) — NOT
// under /admin. Mount alongside the drawer shell + hotkey like the current
// scaffold does (see `src/App.jsx` → `/lara` route).
export function DemoLaraPage() {
  return <LaraFull mode="demo" />;
}

// Re-exports so the human has everything addressable from a single module entry.
export {
  LaraFull,
  ConversationsList,
  ConversationDetail,
  DocumentsPage,
  MemoryPage,
};
