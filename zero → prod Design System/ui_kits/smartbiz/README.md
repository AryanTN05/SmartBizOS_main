# SmartBiz OS — Product UI Kit

Zero → prod's **first shipped product** and flagship agency demo. Multi-module AI business OS where Jarvis (conversational layer) reads/writes across every module via MCP tool calls.

> **Brand relationship:** this kit is a **product skin** over the zero → prod core brand. Same cyan accent, same Geist + Bricolage Grotesque, same square corners, same bold declarative voice. Density bumped up for dashboards.

## Modules in scope

| | Module | Status in kit |
|---|---|---|
| M1 | Jarvis — conversational layer | ✅ right-side drawer, tool-call cards, slash menu, token counter |
| M2 | Sales Intelligence — CRM + scoring | ✅ Kanban board + lead drawer with score explainer + timeline |
| M3 | Automation — Inngest workflows | ✅ runs list + step timeline with step.run / step.sleep / step.waitForEvent |
| M6 | Reports — weekly narrative | ✅ Jarvis-written narrative + charts + source breakdown |
| — | Auth / demo mode | ✅ anonymous "5-min demo" split-screen splash |
| — | Docs / RAG | placeholder only — flag for V1 |

## Files
- `tokens.css` — product-skin overrides over `../../colors_and_type.css`
- `Primitives.jsx` — `SBIcon`, `SBChip`, `SBButton`, `SBKbd`, `SBAvatar`, `SBCard`, `SBStat`, `SBDivider`
- `Chrome.jsx` — `SBSidebar` (72px icon-rail), `SBTopBar`, `DemoCountdown`
- `Jarvis.jsx` — `JarvisDrawer` with tool-call cards, slash commands, voice mic button
- `Leads.jsx` — `LeadsView` Kanban + `LeadCard` + `LeadDrawer` with score rubric
- `Automation.jsx` — `AutomationView` runs list + `RunDetail` + `ReportsView`
- `SignIn.jsx` — anonymous-demo splash + `Home` dashboard

## Decisions worth knowing
- **Jarvis = drawer, not a separate page.** Keeps it one click from anywhere; every module page has "Ask Jarvis" buttons that open it.
- **5 module colors:** cyan (accent/live), violet (Jarvis-authored/AI), warm (in-progress/warm lead), hot (hot lead/failed), lime (completed/won), cool (info/fintech).
- **Mono-font labels everywhere** (uppercase 10px tracking-wide) — signals "this is a technical, MCP-wired product" without being precious.
- **Corner brackets (`.sb-brackets`)** — signature motif on cards that "matter" (Jarvis suggestions, score explainer). Terminal-viewport feel without overdoing it.
- **Tool-call cards** in Jarvis — mono, namespaced (`get_leads`), with args + result. Mirrors the MCP protocol the backend speaks.

## Known gaps (flag for user)
- No Fintech module (M7) — deferred per user direction.
- No Docs surface — placeholder only.
- No mobile layout — dashboards are desktop-first; mobile is a separate pass.
