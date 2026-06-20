# modules/leads — M2 Sales Intelligence

Module root for Leads / CRM / Kanban / Scraper UIs.

## You own

- `components/` — kanban board, lead detail panel, scraper run list, etc.
- `pages/` — index (kanban), detail, scraper runs, enrichment, etc.
- `routes.jsx` — wire sub-routes under `/admin/leads`. The parent route is already a stub in `src/App.jsx`; replace it with your `<Routes>`.

## You import

- `api` from `src/lib/api.js`.
- Primitives from `src/components/primitives`.
- `useLaraUI()` to hand off: `openDrawer({ prompt: 'summarise lead ...', leadId })`.
- `useConfig()` to gate on `config.features.scraper_live_enabled`.

## API surface

See `docs/specs/api-contracts/m2-sales-intel.md`. Relevant backend already has `/api/leads/*` and scraper endpoints scaffolded.
