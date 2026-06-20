# SmartBiz OS — Frontend

Vite + React (JSX) app. Dark-only, cyan accent, square corners. Consumes the FastAPI backend at `../backend` (proxied at `/api`).

## Run

```bash
npm install
npm run dev       # http://localhost:5173 (proxies /api → http://localhost:8000)
npm run build
npm run preview
```

Backend not running? The app still boots — `useSession()` falls back to `{ kind: "anon" }` and `useConfig()` to sensible defaults.

## Layout

```
src/
  main.jsx                    # entry
  App.jsx                     # router + providers
  styles/                     # brand.css + tokens.css + global.css (keyframes)
  components/
    primitives/               # SBIcon, SBChip, SBButton, SBKbd, SBAvatar, SBCard, SBStat, SBDivider
    chrome/                   # SBSidebar, SBTopBar, DemoCountdown
    lara/                     # LaraDrawerShell (stub — module agent replaces)
  lib/
    api.js                    # fetch wrapper — credentials: 'include', error envelope
    SessionContext.jsx        # useSession(), useConfig()
    LaraUIContext.jsx         # useLaraUI() { open, openDrawer, closeDrawer }
  pages/                      # DemoLanding, DemoExpired, AdminLogin, NotFound, admin/Home
  modules/
    lara/ leads/ automations/ reports/ fintech/   # module-agent territory
```

## Module agents

Each module owns `src/modules/<name>/` and registers routes inside `App.jsx`'s admin shell. Import shared code from:

- `src/components/primitives` (barrel)
- `src/components/chrome`
- `src/lib/api`
- `src/lib/SessionContext`
- `src/lib/LaraUIContext`

Don't touch `styles/` or `components/primitives/` — those are the brand surface.
