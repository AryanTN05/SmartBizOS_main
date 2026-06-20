# zero → prod — Design System

A consolidated brand, content, and UI-kit system for **zero → prod** (also written as *zerotoprod*) — a hands-on product agency that takes an idea from **zero to a deployed, production-ready product**.

> "We take your idea and build it into a real, deployed product."
> — hero copy, landing page

## What is zero → prod?

A small, specialized product-engineering team (the site quotes "10+ engineers") that spans **AI / ML integration, full-stack web, mobile, backend, and DevOps**. They run fixed-scope, fixed-price engagements (MVPs in 2–3 weeks), ship through weekly demos, and stay on for a 30-day post-launch support window. Positioned against the "hire a dev team / agency / freelancer" market — "freelancers disappear. Agencies overcharge."

**Calls to action:** `Book a Call` → `https://cal.com/zerotoprod/30min`, email `hello@zerotoprod.tech`.

## Products / surfaces represented

There is currently **one public surface**:

1. **Landing page** — single-page marketing site with
   - scrolling hero w/ interactive "Build Story" panel (napkin → wireframe → design → code → live)
   - services grid, process steps, portfolio, FAQ, about, CTA, marquees
   - **10 enterprise case studies** at `/case-studies/<slug>` (Creative Automation, Legal Auditor, Lead Intelligence, Digital Twin, Finance Reconciliation, Finance Copilot, Operations Intelligence, Personalization Engine, Industrial Edge, Clinical Copilot)

No product app, docs site, or mobile app is represented in the codebase.

## Sources

- **Codebase:** `Landing-Page/` (attached, read-only). React 19 + Vite + Tailwind 4 + framer-motion + react-three-fiber + Spline. See `Landing-Page/src/index.css` for tokens.
- **Brand assets:** `Landing-Page/public/*.svg` + `*.png` (logos, LinkedIn banner, case-study screenshots).
- **No Figma, deck, or external brand guide was attached.**

## Index of this design system

```
README.md                     ← you are here
SKILL.md                      ← agent skill manifest
colors_and_type.css           ← ready-to-import CSS variables for color + type
assets/                       ← logos, icons.svg, case-study renders
reference/flowIcons.ts        ← 12 inline SVG icons used in case-study pipelines
preview/                      ← design-system tab cards (color, type, buttons, …)
ui_kits/
  landing/
    README.md
    index.html                ← interactive recreation of the landing page
    *.jsx                     ← components (Navbar, Hero, Services, Process, …)
```

---

## Content fundamentals

**Brand wordmark:** `zero → prod` — lowercase, with a literal `→` arrow between the two words. The composite phrase "zero to production" is used in long-form copy. Internal/repo name: `zerotoprod`.

**Voice:** direct, grounded, slightly warm. Sentences are short. No MBA-speak, no exclamation marks, no emoji. Copy reads like a competent engineer speaking plainly — confident without being salesy.

**POV:** **"we"** for the team, **"you"** for the reader. Never "our clients" / "our partners." Always addresses the founder/reader in second person.

**Casing:**
- UI buttons & nav: **Title Case** (`Book a Call`, `See Our Work`, `View all case studies`).
- Section titles: **Sentence case**, always punctuated with a period (`Everything you need to ship.`, `Four steps. One product.`, `Why zero → prod exists.`).
- Eyebrows: **UPPERCASE**, tracked at `0.2em` (`CAPABILITIES`, `PROCESS`, `SELECTED WORK`, `ABOUT`, `FAQ`, `LET'S WORK TOGETHER`).

**Punctuation:**
- em-dashes `—` (not `--`) for asides, breath breaks, and emphasis.
- en-dashes `–` inside number ranges (`2–3 weeks`, `250–400 variants/day`).
- Arrow `→` is a brand motif — used in the wordmark, CTAs ("See Our Work →"), case-study navigation, and "zero → production" headings.

**Numbers:** written as numerals with unit (`10+ engineers`, `2–3 weeks`, `92–97%`, `80%+ faster to live`). Metrics are compact: `400/day`, `70–85%`.

**Concrete copy examples (verbatim):**

- Hero: *"From zero to production."* / *"We take your idea and build it into a real, deployed product."*
- Services: *"Everything you need to ship."* / *"Full-stack web apps built for scale — from MVPs to enterprise-grade platforms."*
- Process: *"Four steps. One product."* / *"Wireframes, architecture diagrams, and a clear technical roadmap. You know exactly what we're building and why before we start."*
- About: *"Why zero → prod exists."* / *"We started zero → prod because we saw the same problem everywhere — people with great ideas and no way to build them. Hiring a full dev team is expensive. Freelancers disappear. Agencies overcharge and underdeliver."*
- CTA: *"Ready to go from zero to production?"* / *"Tell us about your idea. No commitment, no jargon, no sales pitch."*
- FAQ tone: *"We'll give you a detailed timeline after our discovery call — and we stick to it. No endless slipping deadlines."*

**Emoji:** never. The design uses the literal arrow `→` as its only "glyph" flourish.

---

## Visual foundations

### Color

The site is **pure dark mode** — light mode is commented out of the CSS because it was unstable. Black (`#08080a`) is the canvas, white-ish grey (`#e8e8e8`) is text, and a single signal color — **cyan/mint `#00ffe0`** — is used sparingly for accents, glows, CTAs, and selections. Everything else is a neutral greyscale.

- **Surfaces:** `--bg-primary #08080a` (page) → `--bg-secondary #101012` (sections) → `--bg-card #151517` (cards) → `--bg-card-hover #1c1c1f`.
- **Text:** `--text-primary #e8e8e8` → `--text-secondary #888888` → `--text-tertiary #484848`.
- **Borders:** `--border-subtle #1a1a1c` (everywhere) → `--border #222224` (stronger dividers).
- **Signal:** `--accent #00ffe0` with `--accent-glow rgba(0,255,224,0.12)`.
- **Brand (logo):** the `ZP` mark is a **blue→green gradient** (`#2c5cf0` → `#3dd871`) on a white/transparent ground. This gradient lives **inside the logo** only; it is *not* used as a background or accent anywhere else on the site.
- **Case-study accents:** each enterprise case study has its own flow-diagram accent — violet `#c084fc` (creative), cyan `#00ffe0` (legal), emerald `#34d399` (lead intel), etc. See `enterpriseCaseStudies*.ts` for the full set.

### Typography

- **Primary typeface: Bricolage Grotesque** (Google Fonts, variable, opsz 12–96, wght 200–800). Used for headlines, body, UI — everything.
- **Numeric/display stretch: Mona Sans** (github/mona-sans variable, stretch 75–125%). Used once — as the thin, condensed `01 / 02 / 03 / 04` numerals in the Process section.
- **DM Sans** is loaded in `index.html` but not actually applied in styles — treat as optional fallback only.
- Headings are `font-weight: 800` with tight tracking (`-0.03em` to `-0.04em`) and short leading (`line-height: 0.9–1`). Body is `1.6`, marketing paragraphs step up to `1.8`.

### Backgrounds

- Flat near-black canvas — **no gradient washes, no illustrations, no hand-drawn art**.
- **Signature background treatment:** a faint grid (`64px × 64px`, 1px `--text-secondary` lines at 5% opacity) radially masked to the center so it fades into black at the edges. Only in the hero section.
- **Interactive 3D hero background** (`scene.splinecode`, runs through a CSS `sepia → hue-rotate(130deg) → saturate(3) → brightness(1.2)` filter to force everything to cyan). Lazy-loaded on capable devices only.
- **Grain overlay** over the whole page — SVG `fractalNoise` baseFrequency `0.9`, numOctaves `4`, opacity `0.03`, re-opacified to `0.4` at compositor. Adds film texture. Always-on.
- Section alternation: most sections are `--bg-primary`; every other one is bumped to `--bg-secondary` (`Process`, `FAQ`).

### Animation

- **Easing: `cubic-bezier(0.16, 1, 0.3, 1)` (ease-out-quint)** — used everywhere framer-motion appears. No bounces, no elastics. Nothing overshoots.
- **Reveal pattern:** `ScrollReveal` wraps most blocks — `opacity 0 → 1` + a 50px slide-in from `up` / `left` / `right`, `once: true`, `margin: -80px`, `duration: 0.7s` (stagger children by `i * 0.08–0.15s`).
- **Hero entry:** staggered `y: 50 → 0` opacity fades at `0.3s / 0.5s / 0.9s / 1.1s` delay, duration `1.1s`.
- **Hover on tiles:** 3D tilt (`rotateX/rotateY ±5°` driven by mouse position, springed `stiffness 300, damping 30`). Border changes from `--border-subtle` → `--accent`. A radial glow layer fades in from 0 → 100% in 500ms.
- **CTA hover:** glow intensifies (`box-shadow: 0 0 30px rgba(0,255,224,0.3)` → `0 0 40px rgba(0,255,224,0.35)`), scale `1.03`, `0.98` on tap.
- **Navbar:** hides on scroll-down, shows on scroll-up (translateY 0 / -100%, 300ms easeInOut).
- **Reduced-motion:** globally respected — `animation-duration` / `transition-duration` forced to `0.01ms`.

### Hover & press states

- **Primary buttons:** cyan `#00ffe0` fill → on hover, add `box-shadow` glow (`0 0 30px rgba(0,255,224,0.3)`). An internal white overlay slides up on hover (`bg-white/20 translate-y-full → 0`, `mix-blend-overlay`, 500ms) to subtly shine.
- **Ghost buttons:** no background; tracking animates wider on hover (`0.02em → 0.1em`, 300ms).
- **Cards:** border shifts from `--border-subtle` → `--accent`; inset radial-gradient glow fades in; contained number pill flips from tertiary to `--accent`.
- **Links / list items:** opacity dim on hover (`opacity: 0.6–0.7`, 200ms).
- **Press:** `whileTap={{ scale: 0.98 }}` on primary CTAs. No color shift.

### Borders, corners, cards

- **Default corner:** **square** — `border-radius: 0`. Primary CTAs, nav pill, service cards, project cards are all hard-edged.
- **Exceptions:** stat card in About (`rounded-2xl` ≈ 16px), project cards' inner image slot (`rounded-lg` ≈ 8px), case-study images (`rounded-lg`).
- All cards use `1px solid var(--border-subtle)` on a `var(--bg-card)` fill. No drop shadow — **glow replaces shadow** across the system. `box-shadow` is always a cyan halo, never a black drop.

### Protection / capsules

No "protection gradient" strips over imagery. No pill/capsule chips for nav (nav links are plain text). Tag chips on service cards are tiny rounded `rounded` pills (`2px` radius) filled `--bg-secondary` with tertiary text — purely utilitarian.

### Layout rules

- **Max widths:** nav `max-w-6xl` (72rem), hero content `max-w-2xl` inside a `55/45` split, section content `max-w-5xl` (80rem), FAQ `max-w-2xl` (42rem).
- **Horizontal padding:** `px-6` (24px) on mobile → `px-12` (48px) on desktop for hero; `px-6` elsewhere.
- **Section rhythm:** `py-28` (112px) top+bottom for section blocks; `py-32` for the final CTA.
- **Fixed elements:** sticky nav, sticky hero (`sticky top-0 h-screen` inside a `minHeight: 400vh` scroll-driven section), scroll-progress bar, scroll-to-top button, custom cursor (desktop only).
- **Grid:** services use a 3-col grid on desktop with a featured `md:row-span-2` card on the left; process is 2-col; portfolio is a stacked full-width list; team is 4-col.

### Transparency & blur

- Navbar: `backdrop-blur-xl` with `color-mix(in srgb, var(--bg-primary) 94%, transparent)` background — only on `md:+`.
- Mobile menu: `backdrop-blur-2xl` + `color-mix(... 95% ...)`.
- CTA: a single `blur(200px)` cyan glow disc behind the headline at 6% opacity.
- Cards never use backdrop-blur.

### Imagery

- Case-study renders are **dark UI screenshots** — near-black backgrounds, thin 1px strokes, glowing nodes, each key-lit in that case study's accent hue. Very cool/technical, slightly synthetic, never warm. No photography of people, no stock imagery.
- Hero 3D: violet-purple asset forced to cyan via CSS filter — so even "colour" imagery ends up cyan-on-black.
- No grain or warm filter on imagery; the only grain is the global page-level noise overlay.

### Motifs to remember

- The arrow `→` in the wordmark, CTAs, and case-study headings.
- Animated pipeline spines: a glowing horizontal line with dashed `stroke-dasharray` marching + `circle` particles traveling along it + pulsing node rings every `0.75s`.
- Eyebrow pattern: **a 24px accent bar** + space + uppercase label (see `SectionHeader.tsx`).
- Gradient-masked selection color — selecting text turns it cyan-on-black.

---

## Iconography

- **Primary in-product icons:** inlined SVG strokes, **1.3–1.5px stroke, `none` fill, `currentColor`** — see `src/components/flowIcons.ts` (copied into `reference/flowIcons.ts`). 12 icons in a 16×16 coordinate space: `shield, eye, agents, chart, brain, audio, globe, zap, database, medical, factory, memory`. Used inside node circles on the case-study FlowCharts.
- **Nav & mobile menu:** inline SVG, 16–20px, `stroke-width: 1.5`, `fill: none`, `currentColor`. No icon font.
- **Social glyphs:** `public/icons.svg` ships a `<symbol>` sprite for `bluesky`, `discord`, `documentation`, `github`, `social` — referenced via `<use href="#github-icon"/>` pattern (copied to `assets/icons.svg`). Solid fills, no stroke; discord + github use `#08060d`, documentation + social use `#aa3bff` stroke.
- **No icon-font dependency** (Lucide, Phosphor, Heroicons, etc.) is installed in the codebase — everything is hand-inlined.
- **Emoji:** never used in the UI. Do not use.
- **Unicode as glyph:** `→` (right arrow, `\u2192`) is used as a brand element in the wordmark, nav CTAs, and case-study links. `+` (plus) is used as the FAQ expander, rotating 45° to become an `×` when open.
- **Logos:** `assets/ZP_Logo.svg` (full wordmark), `assets/ZP_Logo_S.svg` (mark only), `assets/Master_logo1-removebg.png` (used as favicon + nav), `assets/Master_Logo_Full.png` (with wordmark), `assets/LinkedIn_Banner.png` (footer variant).

If an icon is missing from the inlined set, substitute with **Lucide** (https://unpkg.com/lucide-static) at `stroke-width: 1.5` — visually closest match — and flag the substitution.
