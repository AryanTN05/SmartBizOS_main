# modules/reports — M6 Reports

Module root for weekly reports, charts, and on-demand generation.

## You own

- `components/` — chart wrappers (recharts is installed), narrative block, period picker.
- `pages/` — reports list, detail, compare.
- `routes.jsx` — sub-routes under `/admin/reports`.

## You import

- `api` from `src/lib/api.js`.
- `recharts` for visualisations.
- Primitives from `src/components/primitives`.
- Shares space with Fintech (`modules/fintech/`) — feel free to lift shared chart primitives out into a `modules/_shared/` folder by convention if both modules need them.

## API surface

See `docs/specs/api-contracts/m6-reports.md`.
