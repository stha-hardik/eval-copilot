# UI kit (shared class names; `public/css/app.css` implements them)

Look: "Tactile Calm" (see `docs/REDESIGN.md` and the owner's `tactile_calm/DESIGN.md`). Plain HTML + CSS + vanilla JS.
No React, no build step, no framework CSS. Light theme only. Every page:

```html
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>… · Eval Co-pilot</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/css/app.css">  (+ the page's own css file)
</head><body>
… <script src="https://unpkg.com/lucide@0.460.0/dist/umd/lucide.min.js"></script>
<script src="/js/api.js"></script><script src="/js/ui.js"></script><script src="/js/<page>.js"></script>
```

Icons: Lucide only, `<i data-lucide="name" aria-hidden="true"></i>`, then call `lucide.createIcons()` after
inserting HTML. 20px in buttons, 16px inline. No emojis anywhere.

## Tokens (CSS custom properties on `:root`)
- Surfaces: `--canvas #E6ECF4` (cards, inputs, buttons), `--page #EEF3F9` (body), light `--hi #fff`, shade `--lo #C8D2E0`.
- Text: `--text #2E3A4F`, `--muted #6B7A90`. Accent: `--accent #5B7FAE`, `--accent-strong #395E8B` (links, hover),
  `--accent-soft #7A9CC6`.
- Status (each has colour for the dot, `-text`, `-bg`): `--pass`, `--fail`, `--cant`, `--human`.
- Shadows: `--raise-1` (cards), `--raise-2` (modals, toasts), `--raise-sm` (buttons, small chips), `--raise-hover`,
  `--inset` (inputs), `--inset-sm` (trays, tracks), `--inset-xs`, `--primary-shadow`.
- Radius: `--r-sm 12px`, `--r 16px` (buttons, inputs), `--r-lg 24px` (cards, modals), `--r-pill`.
- Spacing: `--space-xs 6`, `--space-sm 12`, `--space-md 20`, `--space-lg 32`, `--space-xl 48`; `--margin` is the page
  side margin (48px desktop, 32px tablet, 20px phone); `--gutter` the grid gap.
- Type: Plus Jakarta Sans 400 / 600 / 700. h1 40/50 bold (30/38 on phones), h2 24, h3 18. Body 16, small 14.
  `.eyebrow` / `.label-caps` = 11px bold uppercase, 0.06em. Paragraphs max 68ch.
- Motion: `--ease-out`, `--ease-out-quint` (entrances), `--ease-out-expo` (signature moments),
  `--t-press 120ms`, `--t-state 220ms`, `--t-layout 360ms`, `--t-enter 560ms`.
- The old names (`--surface`, `--border`, `--s1..--s7`, `--radius`, `--text-strong`, `--accent-tint` …) still exist as
  aliases so unrestyled pages keep rendering; use the new tokens in new CSS.

Depth comes only from shadows. No borders (except the 2px accent keyboard focus ring, offset 3px). Animate only
`transform` and `opacity`; never width/height/top/left. The `prefers-reduced-motion` block is in app.css.

## Classes
Layout: `.topbar` (see below), `.container` (max 1280px, `--margin` side padding), `.page-head` (optional `.eyebrow`,
`h1`, one-line `p`, and the one primary action; wraps on phones), `.stack` (20px gap), `.stack-lg` (32px gap),
`.row` (flex, 12px gap, wraps), `.spacer` (flex:1), `.muted`, `.small`, `.truncate`, `.sr-only`.

Surfaces: `.card` (raised, 24px radius, 32px padding, 20px on phones; never nest a card in a card),
`.section-title`, `.icon-tile` (48px debossed square holding an icon), `.tray` (debossed inner box).

Buttons (min height 48px; 44px touch target on phones): `.btn` (raised secondary look by default), `.btn-secondary`
(same, named for clarity), `.btn-primary` (filled accent, ONE per screen), `.btn-ghost` (no surface until hover),
`.btn-danger` (destructive only), `.btn-sm` (40px, 44px on phones), `.btn-block` (full width), `.icon-btn`
(44x44 raised, needs `aria-label` + `title`; `.is-flat` for no shadow). Hover softens the shadow, press goes inset and
`scale(.98)`. `[aria-busy=true]`, `:disabled` (50%), `:focus-visible` ring. `EC.busy` still works (it swaps the
button's innerHTML).

Forms: `.field` wraps `.label` + `.input` (`textarea.input`, `select.input`) + `.hint` + `.error-msg`. Inputs are
debossed troughs; `.input.is-error` adds a clay-red inner ring. Leading icon / trailing control:
```html
<div class="input-wrap has-icon has-trail">
  <span class="input-icon" aria-hidden="true"><i data-lucide="at-sign"></i></span>
  <input class="input" …>
  <button class="input-trail" type="button" aria-label="Show password">…</button>   <!-- or span.input-trail.is-static -->
</div>
```
Controls that appear more than once are ONE component each (styles in `app.css`, behaviour in `ui.js` as `EC.ui.*`).
Page CSS may only position them. See "Components" below.

Progress: `.progress` (debossed 12px track; `.progress-sm` 8px) > `.progress-fill` with `style="--p:0.7"`
(fill is `transform: scaleX(var(--p))` from the left and draws in on load; `.is-pass` sage, `.is-fail` clay, default
accent). Legacy `.progress > span` with an inline `transform:scaleX()` also still works. Give the track
`role="progressbar"` + aria values.

Table: `.table-wrap` (overflow-x auto) > `table.table` (caps header, engraved groove between rows). On phones
`table.table.stack-mobile` turns each row into a block, with `td[data-label]::before` labels.

Feedback: `.spinner`, `.skeleton` (debossed with a shimmer; `.skeleton-card` is a card-shaped one), `.empty`
(centered; icon in `.empty-icon`, title, one line, one action), `.banner` + `.banner-error` / `-info` / `-success`
(optional `.banner-icon` bubble and `.banner-body` > `.banner-title` + plain line), `.toasts` / `.toast` /
`.toast-success|error|info` / `.toast-out` (made by `EC.toast`).

Modal: `.modal-backdrop` > `.modal` (max 560px; `.modal-head` with `.eyebrow`, `h2`, subtitle; `.modal-close`
`.icon-btn` top right; `.modal-actions` = Cancel `.btn-ghost` + one primary). To close with animation add
`.is-closing` to the backdrop, then remove it after about 300ms (see `openForm` in `public/js/home.js`).

Motion utilities: `.enter` (fade up 8px, 560ms; stagger with `style="--i:N"`, delay = min(N,6) x 60ms),
`.pop`, `.settle` (login logo). Note `.enter` and `.pop` use fill-mode `both`, so do not put a hover `transform`
on the same element (wrap it: `li.enter > .card`).

Home page pieces: see Stat tile and Project card under Components.

## Components (define once, reuse everywhere)
If a control is already here, use it; never restyle its look or motion in a page file (placement and margins only).
All motion is `transform` / `opacity` (plus the stat ring's `stroke-dashoffset`) and is skipped for
`prefers-reduced-motion` (CSS block in `app.css`; JS animations check `EC.ui.reducedMotion()`).

| Component | CSS (`app.css`) | JS (`ui.js`) | Used by |
|---|---|---|---|
| Top bar | `.topbar`, `.brand`, `.avatar`, `.tabbar` | `EC.ui.topbar(opts)` | home, project, run |
| Segmented control | `.segmented`, `.segmented-btn`, `.seg-indicator` | `EC.ui.segmented(el)` | login Log in / Sign up, project filter All / Priority / Suggested |
| Tabs | `.tabs`, `.tab`, `.tabbar` | `EC.ui.tabs(el)` (made by `topbar`) | top bar + phone bottom bar |
| Switch | `.switch` | `EC.ui.switchHtml(o)` | pair "Approved" |
| Icon toggle | `.icon-btn.icon-toggle` | `EC.ui.iconToggle(el)`, `.set(btn, on)`, `iconToggleHtml(o)` | pair Priority star, voice mic |
| Checkbox | `.checkbox` | none | re-run pair pickers |
| Disclosure | `details.disclosure`, `.disclosure-btn` | `EC.ui.disclosure(details, open?)` (automatic for every `details.disclosure`) | "How to read this", result "Checks (N)", "More / Less" |
| Menu | `.menu`, `.menu-item`, `.menu-wrap` | `EC.ui.menu(button, menuEl)` | avatar menu |
| Status pill | `.pill` + `.pill-*` | `EC.ui.pill(kind, text, {pop})` | everywhere a status is shown |
| Chip | `.chip`, `.chip-sm` | none | "N sites", site link, device tag |
| Stat tile | `.stats` > `.stat`, `.ring` | none | home |
| Project card | `.project-card`, `.run-tray`, `.add-tile` | none | home |

### Top bar: `EC.ui.topbar({ page, projectId, projectName, runId, runNumber })`
Put `<header class="topbar" id="topbar"></header>` on the page and call it once, early. `page` is `"home"`, `"project"`
or `"run"`. It renders the brand tile, the four tabs (My projects, Golden tests, Runs & results, Compare), a real
"Log out" and the avatar menu (which shows the email in `#user-email`; both log-out buttons
call `EC.logout()`). On phones (<= 640px) the bar shrinks to brand tile + page title + avatar and the tabs become a
fixed bottom bar (the component adds `<nav class="tabbar" id="tabbar">` to `<body>` and `body.has-tabbar`).
Returns `{ update(opts), setActive(key), el }`; call `update({ projectId, projectName, runId, runNumber })` once the page
has its data. Tabs link to the page's own project / run, else the last opened ones remembered in `localStorage`
(`ec.lastProject`, `ec.lastProjectName`, `ec.lastRun`, plus `ec.lastRunProject` so a run is never offered under another
project); an unknown target is a disabled tab (`aria-disabled`, "Open a project first"). Pages call
`EC.ui.remember({ projectId, projectName, runId })` after their data loaded. On the run page the Runs & results and
Compare tabs do not reload: they scroll and slide the indicator (Compare sets `#compare`). Logging out forgets the
remembered ids. The project page's sticky run bar sits above the bottom tab bar; do the same for any other fixed bar
(`bottom: calc(64px + env(safe-area-inset-bottom, 0px) + var(--space-sm))`).

### Segmented control and tabs
```html
<div class="segmented" role="group" aria-label="Show">
  <button type="button" class="segmented-btn" data-value="all" aria-pressed="true">All</button>
  <button type="button" class="segmented-btn" data-value="priority" aria-pressed="false">Priority</button>
</div>
```
`const seg = EC.ui.segmented(el)` adds the single raised `.seg-indicator` that slides (FLIP, 360ms) to the selection,
keeps `aria-pressed` (or `aria-selected` when `role="tablist"`), handles arrow keys / Home / End and emits a bubbling
`change` event (`ev.detail.value`). `seg.select(value, { silent })`, `seg.refresh()` after changing labels. Keep the element
and update its labels in place so the indicator can slide; do not re-create it. Tabs use the same indicator (`EC.ui.tabs`).

### Switch
`EC.ui.switchHtml({ checked, onLabel: "Approved", offLabel: "Not approved", label, attrs: 'data-act="approve"' })` returns a
real `input[type=checkbox][role=switch]` inside `label.switch`; the thumb slides 22px, squeezes while pressed, and the
label word and colour cross-fade. Read `input.checked`; listen for `change`.

### Icon toggle
`EC.ui.iconToggleHtml({ icon: "star", pressed, label, attrs })` gives `button.icon-btn.icon-toggle[aria-pressed]` (raised off,
inset on, icon fills and pops). Page code that flips optimistically calls `EC.ui.iconToggle.set(btn, true|false)` (plays
the pop when turning on); standalone toggles can call `EC.ui.iconToggle(btnOrContainer)` to flip on click and emit
`change`. Add `.is-outline` for icons that should not fill (mic).

### Checkbox
`<label class="checkbox"><input type="checkbox"> text</label>`: inset square, the accent gem pops in with a check, the whole
row (44px) is the hit area.

### Disclosure
```html
<details class="disclosure" open>
  <summary><span class="disclosure-title">How to read this</span><i data-lucide="chevron-down" class="disclosure-chev"></i></summary>
  <div class="disclosure-body">...</div>
</details>
```
No setup needed: one delegated handler animates every `details.disclosure` (content fades and rises on open, fades out
270ms before `open` is removed). Add `.disclosure-inline` for a summary that is not full width. `EC.ui.disclosure(d, true|false)`
opens or closes from code. A small text button that expands something in place uses `.disclosure-btn[aria-expanded]` with the
same chevron.

### Menu
`.menu-wrap` > trigger button + `<div class="menu" role="menu">` with `button.menu-item[role=menuitem]` children.
`EC.ui.menu(button, menuEl)` opens with fade + scale from the trigger corner, closes on Escape / outside click, moves
focus to the first item and back to the button.

### Status pill
`<span class="pill pill-pass">Pass</span>`, or `EC.ui.pill("pass", "Pass", { pop: true })`. Kinds: `pass`, `fail`, `cant`,
`human` (you check), `running` (dot pulses), `neutral`, `priority`, `fixed`, `broke`, `same`. Add `.pop` when a pill first
appears with a result; `.has-icon` keeps a Lucide icon instead of the dot. Never write a page-local pill.

### Stat tile and project card (home)
`.stats` > `.stat` (`.stat-label`, `.stat-value` with `.is-fail` / `.is-pass`, optional `.stat-sub`, raised `.icon-tile`).
The pass-rate tile holds an SVG `.ring` whose `.ring-arc` draws in with `style="--p:<percent>"`. `.project-card`: icon tile,
status pill, name, site link, `.run-tray` (outcome icon + "Last run" text + progress bar), foot with a `.label-caps` tag and
an Open button; hover lifts 2px and cross-fades the shadow. `.add-tile` is the "Add a website" tile. Every number shown comes
from the API (see `public/js/home.js`).

## Shared JS (`/js/api.js` exposes `window.EC`; `/js/ui.js` adds `EC.ui`, see Components)
- `EC.api(method, path, body?)` → JSON; throws `EC.ApiError` (`.status`, `.message` in plain words);
  handles 401 → refresh → retry → redirect to login.
- `EC.requireLogin()` (call first on logged-in pages; returns false and redirects if no session),
  `EC.getSession()` → `{access_token, refresh_token, user:{email}}`, `EC.setSession(s)`, `EC.logout()`.
- `EC.param(name)` reads the query string. `EC.esc(text)` escapes for innerHTML (ALWAYS use it for any
  data from the server or the user). `EC.toast(msg, "success"|"error"|"info")`.
  `EC.busy(button, asyncFn, "Saving…")` greys out a button and shows a spinner while work runs.
  `EC.fmtDate(iso)`.

## Pages
- `/` → `index.html` (log in / sign up), `/home.html` (my projects), `/project.html?id=…` (golden pairs),
  `/run.html?id=…` (results of one run).

## Copy
Plain words, no jargon: say "link" not "URL", "check" not "assertion", "phone" / "laptop" not "device / UA".
Friendly, short. Example: "The site blocked us, so we can't test this."

## M7: real browser
- Check tags (`EC.ui.checkTag`): **Code**, **AI**, **Real browser** (`.pill-browser`, globe icon; for `browser_count` and
  `ai_vision`) and **You check** (only a legacy `manual` check or a check handed to a person at run time).
- `EC.ui.stepsText(steps)` writes a check's browser steps in plain words ("Opens /products/solaris → clicks “Sand”").
- Results rows: a "Real browser" badge when `via` is "browser"; a "You check" badge plus the `human_reason` note when
  `via` is "human".
