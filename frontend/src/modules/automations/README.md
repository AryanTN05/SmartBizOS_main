# modules/automations — M3 Automation

Module root for workflow timelines, templates, runs, and the channel registry.

## You own

- `components/` — timeline graph, step editor, run log viewer.
- `pages/` — timelines list, timeline detail, runs, templates.
- `routes.jsx` — sub-routes under `/admin/automations`.

## You import

- `api` from `src/lib/api.js`.
- Primitives from `src/components/primitives`.
- `useLaraUI()` for "Ask Lara about this run" hand-offs.

## API surface

See `docs/specs/api-contracts/m3-automation.md`.
