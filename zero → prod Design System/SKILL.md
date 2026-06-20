---
name: zerotoprod-design
description: Use this skill to generate well-branded interfaces and assets for zero → prod (zerotoprod.tech), either for production or throwaway prototypes/mocks/decks/landing pages. Contains essential design guidelines, colors, type, fonts, logos, iconography, and a UI kit ported from the production landing page.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files. Key files:

- `README.md` — brand context, content fundamentals, visual foundations, iconography
- `colors_and_type.css` — drop-in CSS variables (`--accent`, `--bg-primary`, `--text-primary`, etc.) plus semantic type classes
- `assets/` — logos (`Master_logo1-removebg.png`, `Master_Logo_Full.png`, `ZP_Logo.svg`), case-study imagery, hero background, banner
- `reference/flowIcons.ts` — 12 stroke-only flow icons used in pipeline diagrams
- `ui_kits/landing/` — pixel-accurate recreation of the marketing site as modular JSX components (Nav, Hero, Services, Process, Portfolio, FAQ, Footer)
- `preview/` — one-off preview cards demonstrating each token and component in isolation

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out of `assets/` and create static HTML files for the user to view. Import `colors_and_type.css` to inherit the brand tokens. For production code, copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask a few questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## Quick brand reminders
- **Dark by default** — `#08080a` page, cyan accent `#00ffe0`, no drop shadows (use cyan glow instead)
- **Square corners by default** — radii are the exception
- **Type** — Bricolage Grotesque for marketing headlines, Geist or Inter for product UI (see `preview/type-display.html` for the 4-way comparison). Weight 500-600 for most things; 700 only for tightly-tracked headlines. **Avoid 800+** — it reads as AI slop.
- **Voice** — confident, calm, declarative. "We ship." Not "We're excited to announce we ship!" Em-dashes welcome. No emoji. No AI slop.
- **Iconography** — stroke-only SVGs at `currentColor`, 1.3-1.5px stroke
