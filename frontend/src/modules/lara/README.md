# modules/lara — M1 Lara

Module root for the Lara conversation layer.

## You own

- `components/` — chat bubbles, tool-call chips, voice mic toggle, etc.
- `pages/` — full-page Lara views (if any beyond the drawer).
- `routes.jsx` (create this) — exports the `<Route>` fragments this module contributes under `/admin`.
- Replace the body of `src/components/lara/LaraDrawerShell.jsx` with the real streaming chat UI (keep the shell: backdrop, panel, header, close button).

## You import

- `@ai-sdk/react` for chat streaming (already in `package.json`).
- `api.stream('/api/lara-smartbiz/chat', body)` from `src/lib/api.js` for SSE.
- `useLaraUI()` from `src/lib/LaraUIContext.jsx` to read `{ open, seed }` — `seed` is whatever the caller passed to `openDrawer(payload)`.
- Primitives from `src/components/primitives` — don't roll your own buttons/chips.

## Routes to wire

- Demo page at `/lara` already exists as `src/pages/LaraFull.jsx`. Replace or wrap it.
- Admin stub at `/admin/lara` should become a full management view.

## Conventions

- Plain JSX, no TypeScript.
- Inline styles or CSS vars; no Tailwind, no CSS-in-JS lib.
- Dark only, square corners, cyan accent.
