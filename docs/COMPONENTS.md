# Component spec (lead → implementer)

Goal: every control that appears more than once is ONE component, defined once in `public/css/app.css`
(styles + motion) and, when it needs behaviour, once in `public/js/ui.js` (exposed as `EC.ui.*`). Pages call
the component; no page CSS file may restyle a component's core look or motion (only its placement).
Rules from `docs/REDESIGN.md` still apply (tokens, eases, durations, reduced motion, no invented numbers).

## 1. Shared top bar: `EC.ui.topbar({ page, projectId, projectName, runId, runNumber })`
Renders into `<header class="topbar" id="topbar"></header>` on every logged-in page (home, project, run).
Matches the My projects mockup:
- Left: brand tile (raised, `check` icon) + "Eval Co-pilot" + label-caps subtitle "WEBSITE QUALITY CO-PILOT"
  (subtitle hidden ≤ 900px).
- Center: **tabs** (Tabs component, §3) "My projects" · "Golden tests" · "Runs & results" · "Compare".
  Real links: My projects → `/home.html`; Golden tests → `/project.html?id=<project>`; Runs & results →
  `/run.html?id=<run>`; Compare → `/run.html?id=<run>#compare`. `<project>` / `<run>` = the page's own,
  else the last opened ones remembered in localStorage (`ec.lastProject`, `ec.lastRun`, `ec.lastProjectName`;
  pages set them when they load; wrap storage in try/catch). Unknown → the tab is `aria-disabled="true"`,
  muted, not focusable as a link, `title="Open a project first"`. Active tab = current page (Compare when
  `location.hash === "#compare"` on the run page; clicking Compare there scrolls smoothly to the compare
  section and moves the indicator without reloading).
- Right: "Log out" (ghost) and an **avatar** button
  (accent circle with the user's first email letter, `aria-haspopup="menu"`) opening the **Menu** component
  (§8) with the email, the **Dark theme** switch (§12) and "Log out".
- Phones (≤ 640px): top bar = brand tile + page title text (short) + avatar only; the 4 tabs move to a fixed
  **bottom tab bar** (icons `layout-grid`, `list-checks`, `activity`, `git-compare` + short labels
  "Projects", "Tests", "Results", "Compare"), raised level 2, safe-area padding
  (`env(safe-area-inset-bottom)`), 64px tall, same active / disabled logic, sliding indicator. Body gets
  bottom padding so nothing is hidden; the project page's sticky run bar sits ABOVE the tab bar.
- Remove the old per-page topbar markup and the old crumb code; the page heads keep their "Back to …" links.

## 2. Segmented control: `.segmented` + `EC.ui.segmented(el)`
Debossed pill container; ONE raised **indicator** element that slides to the selected option
(FLIP: measure old and new option rects, set the indicator to the new rect, start it at
`translateX(dx) scaleX(oldW/newW)` and transition to `none`, 360ms ease-out-quint; `transform-origin: left`).
Selected text colour cross-fades 220ms. Keyboard: arrow keys move selection (role=tablist/tab or
radio-group semantics, `aria-selected` / `aria-pressed` kept as the pages use now). Emits `change`.
Used by: login Log in / Sign up, project filter chips All / Priority / Suggested, the compare picker if it
becomes chips, and internally by Tabs.

## 3. Tabs: `.tabs` (desktop top bar + phone bottom bar) built on the segmented indicator
Same sliding indicator; links instead of buttons. On page load the indicator appears in place (no slide).

## 4. Switch: `.switch` (move from project.css to app.css)
Inset track; thumb slides 22px (220ms ease-out-quint); on `:active` the thumb widens a little
(`scaleX(1.15)`, origin toward the travel direction) for a tactile squeeze; track tint fades in; label word
and colour cross-fade ("Approved" sage / "Not approved" muted). Real checkbox with `role="switch"`.
Used by the pair Approved toggle (and any future on/off).

## 5. Icon toggle: `.icon-toggle[aria-pressed]` + `EC.ui.iconToggle(btn)` (replaces `.toggle`)
Raised → pressed inset when on; turning ON plays a small pop on the icon (`scale 1 → 1.2 → 1`, 280ms) and
fills it; OFF fades the fill (220ms). Used by the Priority star. Optimistic flip stays in the page code.

## 6. Checkbox: `.checkbox` (exists)
Inset 24px square, accent gem pops in (`scale .6 → 1`, 220ms ease-out-quint) + tiny check icon; whole label
row is the hit area (≥ 44px) with a soft press (`scale .99`). Used by the re-run pickers.

## 7. Disclosure: `.disclosure` (wraps `<details>`) + `EC.ui.disclosure(details)`
Summary row with a chevron that rotates 180° (220ms). On open, the content fades in and rises 6px (360ms);
on close, it fades out (270ms) before `open` is removed (JS intercepts the summary click; reduced motion →
instant). Used by "How to read this", each result's "Checks (N)", the "More / Less" excerpt toggle
(make it a disclosure or give it the same chevron + fade), and any other expandable bit.

## 8. Menu / popover: `.menu` + `EC.ui.menu(button, menuEl)`
Raised level 2, `transform-origin` at the trigger corner, opens with fade + `scale .96 → 1` (220ms), closes
in 170ms; Escape and outside click close; focus moves to the first item and back to the button.
Used by the avatar menu.

## 9. Status pill: `.pill` (exists): one place
Capsule + dot + word: pass / fail / can't test / you check / running (dot pulses softly via opacity) /
neutral / priority. When a pill first appears with a result it uses `.pop`. All pages use this; remove
page-local pill variants.

## 10. Stat tile: `.stat`
Label-caps title, big value, raised icon tile on the right; value tone (`.is-fail` → terracotta). The
icon tile for pass rate is a small SVG ring whose arc draws in (stroke-dashoffset, 700ms ease-out-expo;
this tiny SVG is the one allowed non-transform animation).

## 11. Project card: `.project-card` (home)
Per mockup: icon tile (icon chosen deterministically from the project name among `shopping-bag`, `store`,
`globe`, `layout-template`, `calendar`, `file-text`), status pill top-right, name, site link with
`arrow-up-right`, an inset tray with an outcome icon (`circle-check` / `circle-alert` / `bar-chart-2`) +
"Last run: Run N · X of Y passed · date" + coloured progress bar (sage all passed, terracotta with fails,
accent when no results), bottom row: label-caps tag + raised "Open ›" button. Hover: card lifts
(`translateY(-2px)` + shadow cross-fade).

## 12. Theme toggle: "Dark theme" row in the avatar menu
Between the "Signed in as / email" head and "Log out" (the same menu on phones, where the avatar is the only account control).
A full-width row (`.menu-row` > `label.switch.switch-row`, built with `EC.ui.switchHtml({ cls: "switch-row", lead, attrs: "data-theme-switch" })`):
moon icon, "Dark theme", and the switch on the right. Real `input[type=checkbox][role=switch]`, `aria-label="Dark theme"`, checked when
`ECTheme.get() === "dark"`. The whole row is the hit area, 44px tall; Space toggles (native) and Enter toggles too; arrow keys move
between it and "Log out" (`EC.ui.menu` treats `[role=switch]` as a focusable item). Toggling calls `ECTheme.set("dark" | "light")`
and the menu stays open (only `role="menuitem"` closes it). The switch follows the `ec:theme` event, so it stays right if the theme
changes elsewhere (another tab on the same page, the device setting). Colours cross-fade ~250ms; nothing moves; no animation for
reduced motion. Needs `/js/theme.js` first in `<head>`; without `window.ECTheme` the row is not rendered.

## Home page data (all real, from `GET /api/projects`)
- Eyebrow with a small green dot: "YOUR WEBSITES".
- Chip beside "New project": sliders icon + "N sites".
- 4 stat tiles (omit when no projects): **Pass rate** = Σ last_run.passed / Σ last_run.total over projects
  that have a run, one decimal % (ring = that fraction); **Passing results** = "Σ passed / Σ total";
  **Needs attention** = Σ (total − passed) + " items" (terracotta when > 0, sage "Nothing" when 0);
  **Last run** = "Today" / "Yesterday" / date of the newest `last_run.started_at`. No run anywhere → show
  "—" with "No runs yet".
- Card status pill: no run → "Not run yet" (neutral); total 0 → "Review" (amber); all passed → "All passed"
  (sage); else "N issues" where N = total − passed (terracotta). Card tag (label-caps): last run kind
  "FULL RUN" / "RE-RUN", or "NOT RUN YET".
- Add tile: plus-in-circle tile "Add a website" / "Test another site as a phone and a laptop."
