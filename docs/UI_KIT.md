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
<script src="/js/api.js"></script><script src="/js/<page>.js"></script>
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
`.checkbox` wraps `input[type=checkbox]` + text (44px target): inset 24px square, accent gem when checked.

Segmented control (pick one): `.segmented` > `button.segmented-btn[aria-pressed="true|false"]` (or `.is-active`).

Status pills: `.pill` plus one of `.pill-pass` (Pass / All passed), `.pill-fail` (Fail), `.pill-cant` (Can't test),
`.pill-human` (Needs a look), `.pill-fixed`, `.pill-broke`, `.pill-same`, `.pill-neutral`, `.pill-priority`.
Capsule, tint, coloured text, solid dot, always a word. The dot is drawn by CSS; any Lucide icon left inside a
`.pill` is hidden. Add `.pop` to make a pill scale in (.8 to 1, 360ms).

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

Home page pieces (reusable): `.eyebrow`, `.stats` > `.stat` (`.stat-label`, `.stat-value`, `.icon-tile`),
`.project-grid` (3 / 2 / 1 columns), `.project-card`, `.run-tray`, `.add-tile`.

## Topbar and context nav (shared markup)
```html
<header class="topbar">
  <a class="brand" href="/home.html" aria-label="Eval Co-pilot, my projects">
    <span class="brand-tile"><i data-lucide="check" aria-hidden="true"></i></span>
    <span class="brand-name">Eval Co-pilot</span>          <!-- visually hidden on phones -->
  </a>
  <nav class="nav-pills" id="ctx-nav" aria-label="Where you are">
    <a class="nav-pill is-active" href="/home.html" aria-current="page">My projects</a>
  </nav>
  <span class="spacer"></span>
  <span class="user-email" id="user-email"></span>            <!-- hidden on phones -->
  <button class="btn btn-ghost btn-sm" id="logout" type="button">Log out</button>
</header>
```
Crumbs by page (always escape names with `EC.esc`):
- Home: `My projects` is the active pill (above).
- Project page: "My projects" is a plain link, the project name is the active one.
  ```html
  <a class="nav-pill" href="/home.html">My projects</a>
  <span class="nav-pill is-active" aria-current="page">Bubl Solar</span>
  ```
  (If you prefer the project pill to stay a link, use `<a class="nav-pill is-active" href="/project.html?id=…" aria-current="page">`.)
- Run page: project crumb is a link, "Run 3" is active, and "My projects" is not active:
  ```html
  <a class="nav-pill" href="/home.html">My projects</a>
  <a class="nav-pill" href="/project.html?id=…">Bubl Solar</a>
  <span class="nav-pill is-active" aria-current="page">Run 3</span>
  ```
Only one pill carries `is-active` + `aria-current="page"`. Long names truncate (max 220px, 160px on phones). On phones
the pills scroll sideways inside their container, never the page. The old markup (`a.brand` with plain text) still renders.

## Shared JS (`/js/api.js`, already written, exposes `window.EC`)
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
