# Redesign brief: "Tactile Calm" (owner's Stitch mockups) + motion

Source of truth for the look: the owner's mockups (PNG + Stitch `code.html` per screen) in
`/Users/biku/Downloads/stitch_eval_co_pilot_web_app/`:

| Mockup folder | Our page |
|---|---|
| `eval_co_pilot_login` | `/` (`index.html`, `js/login.js`) |
| `eval_co_pilot_my_projects` | `/home.html` (`js/home.js`) |
| `eval_co_pilot_test_a_new_website` | the "New project" modal on `/home.html` |
| `eval_co_pilot_golden_tests` | `/project.html` (`js/project.js`, `css/project.css`) |
| `eval_co_pilot_runs_results` | `/run.html` results part (`js/run.js`, `css/run.css`) |
| `eval_co_pilot_what_changed_after_re_run` | `/run.html` "Good now?" panel after a re-run |
| `eval_co_pilot_compare_runs` | `/run.html` compare section |
| `tactile_calm/DESIGN.md` | the design system rules (read it in full) |

The mockups' HTML uses the Tailwind CDN and Material Symbols. **We do not.** Translate the look into plain
CSS in our own files and keep Lucide icons (already loaded; pick the closest Lucide icon). No build step,
no framework, no React. The features stay exactly what `BUILD_PROMPT.md` sections 2 and 8 and
`docs/API.md` describe: change how things look and move, never what the app does or which doors it calls.

## Leave out (mockup decoration with no real feature behind it)
Do not build these, even as dead links: "Forgot?" password link, "Diagnostics Fleet / Encrypted 256-bit"
strip, "No credit card required…", "All systems operational" pill, the avatar circle menu, "Overall health %",
"Attention needed", "4 active monitors", "Suite capacity", "99.4% stability", "Suite verification
frequency: Hourly", "Deterministic eval", "Desktop & Mobile Active" badge, "Dual Perspective Suite /
ENABLED" box (replace with one plain line: "We test it as a phone and as a laptop."), "Staging Server
Response Delta", "Latency −1.2s vs Run 14", "Download Diff Log", "Review & Fix Issue", "Auto-verified via
Live Engine", "Overall stability 87.5% / +10% net", footer links (Documentation / System Health /
Privacy), fake project tags ("ECOMMERCE CORE"…). Never show made-up numbers: every number on screen comes
from the API.

The top nav tabs in the mockups (My Projects / Golden Tests / Runs & Results / Compare) become a
**context nav**: "My projects" always; on a project page or run page also the project name (links to
`/project.html?id=…`); on a run page also "Run N". Use the mockup's pill-tab look (debossed pill
container, raised active chip). Right side: the user's email (hidden on phones) + "Log out".

## Tokens (put on `:root` in `public/css/app.css`)
```
--canvas:#E6ECF4; --page:#EEF3F9 (body background, very slightly lighter, as in the mockups' surround)
--hi:#FFFFFF; --lo:#C8D2E0;                     /* light / shade for the 135° light source */
--text:#2E3A4F; --muted:#6B7A90;
--accent:#5B7FAE; --accent-strong:#395E8B (hover/pressed, links); --accent-soft:#7A9CC6;
--pass:#7FB89A; --pass-text:#4B7A62; --pass-bg:rgba(127,184,154,.18);
--fail:#D98880; --fail-text:#8E433C; --fail-bg:rgba(217,136,128,.18);
--cant:#E0B872; --cant-text:#876326; --cant-bg:rgba(224,184,114,.20);
--human: accent-soft family (text #3E6187 on rgba(122,156,198,.18))
--raise-1: -8px -8px 18px var(--hi), 8px 8px 18px var(--lo);
--raise-2: -12px -12px 24px var(--hi), 12px 12px 24px rgba(200,210,224,.9);
--raise-hover: -5px -5px 12px var(--hi), 5px 5px 12px var(--lo);
--inset: inset 4px 4px 8px var(--lo), inset -4px -4px 8px var(--hi);
--inset-sm: inset 3px 3px 6px var(--lo), inset -3px -3px 6px var(--hi);
--primary-shadow: 4px 6px 14px rgba(91,127,174,.35), -3px -3px 8px var(--hi);
--r-sm:12px; --r:16px (buttons, inputs); --r-lg:24px (cards, modals); pills 9999px
spacing 6 / 12 / 20 / 32 / 48 (space-xs…xl); page side margin 48px desktop, 20px phone
```
Font: **Plus Jakarta Sans** 400/600/700 from Google Fonts (replaces Inter). Type scale from DESIGN.md
(headline-xl 40/50 bold −0.02em, 30px on phones; headline-md 24; title-md 18 semibold; body-md 16;
body-sm 14; label-caps 11px bold uppercase 0.06em). Paragraphs max ~68ch.

Depth only through shadows on the same base colour; no borders except the focus ring
(`2px solid var(--accent)`, `outline-offset:3px`). Inputs are debossed troughs (`--inset`), cards raised
(`--raise-1`), the one primary button per screen is filled accent with `--primary-shadow`, secondary
buttons are raised canvas. Status pills: capsule, tint background, coloured text, a solid coloured dot,
and always a word ("Pass", "Fail", "Can't test", "You check"). Light theme only (the design is a single
lit surface); keep contrast AA for text.

Phones (≤ 640px): every multi-column area stacks into single cards, 20px side margin, no sideways page
scroll, touch targets ≥ 44px. Check at 390px and 1280px wide.

## Motion (owner's kole-uiux-skills `references/animation.md`, condensed)
Purpose over decoration; **one signature moment per screen**, everything else quiet micro-feedback.
Animate **only `transform` and `opacity`** (shadows may cross-fade via a pseudo-element's opacity, never
animate width/height/top/left). Default easing is smooth deceleration, never linear, no elastic overshoot.

```
--ease-out: cubic-bezier(0.25,1,0.5,1);      /* quart: default */
--ease-out-quint: cubic-bezier(0.22,1,0.36,1); /* entrances */
--ease-out-expo: cubic-bezier(0.16,1,0.3,1);   /* the signature moment */
--t-press:120ms; --t-state:220ms; --t-layout:360ms; --t-enter:560ms;  /* exit ≈ 75% of enter */
```
- Press (all buttons): 120ms, shadow goes to inset + `scale(.98)`; hover 220ms softens shadow to
  `--raise-hover` (use an `::after` layer with the alternative shadow and fade its opacity).
- Page load: content blocks fade up 8px, 560ms ease-out-quint, staggered 60ms (max ~6 steps, then no
  extra delay). Cards in a list use the same stagger.
- Modal: backdrop fade 220ms; panel fade + rise 12px + scale .98→1, 360ms; close ≈ 270ms.
- Toast: slides up 16px + fade, 360ms; leaves 270ms.
- Progress bars: fill uses `transform: scaleX()` from the left, 560ms ease-out-expo.
- Tooltips (if any): appear after ~1000ms hover.
- Skeletons: soft shimmer (transform on a pseudo-element), not a pulsing layout.
- **Signature moments:** login: the logo tile settles in (rise + gentle scale .96→1, 700ms expo).
  Results page: each row slides in as its pair finishes and its status pill "pops" (scale .8→1, 360ms
  ease-out-quint) while the top progress bar draws forward. "Good now? Yes" button-pill gets one gentle
  scale-in when the panel appears.
- Optimistic UI where safe (e.g. the Approved / Priority toggles flip at once, revert with a toast if the
  door fails).
- Mandatory: `@media (prefers-reduced-motion: reduce){ *,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important} }`.

Never: motion with no purpose, >500ms on feedback, blocking input during an animation, animating everything.

## Rules that still apply
- Plain words on screen ("link", "check", "phone", "laptop"). Keep every loading / empty / error / success
  state (restyled, not removed). Keep `EC.esc()` on every piece of server or user text put in innerHTML.
- Keep every element id and data attribute that the page's JS relies on, or update the JS in the same
  change. Keep every door call and its order exactly as it is.
- Keep `/js/api.js` unchanged (shared; owned by the lead).
