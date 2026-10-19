# UI kit (shared class names; `public/css/app.css` implements them)

Plain HTML + CSS + vanilla JS. No React, no build step, no framework CSS. Every page:

```html
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>… · Eval Co-pilot</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/css/app.css">  (+ the page's own css file)
</head><body>
… <script src="https://unpkg.com/lucide@0.460.0/dist/umd/lucide.min.js"></script>
<script src="/js/api.js"></script><script src="/js/<page>.js"></script>
```

Icons: Lucide only (one family), `<i data-lucide="name" aria-hidden="true"></i>`, then call
`lucide.createIcons()` after inserting HTML. 20px in buttons, 16px inline. No emojis anywhere.

## Design tokens (CSS custom properties on `:root`, dark mode under `prefers-color-scheme: dark`)
- Font: Inter, weights 400 and 600 only. Sizes: 13, 14, 16 (base), 20, 24px max. Body line-height 1.5,
  headings 1.2.
- Spacing: 4px grid: 4, 8, 12, 16, 24, 32, 48. Default gap between blocks 32px.
- Radius: one value `--radius: 10px` (inputs, buttons, cards); pills fully round.
- Neutrals (light): page `#f7f7f8`, surface `#ffffff`, raised `#fbfbfc`, border `#d9d9de` (~85% white),
  text `#1c1c1f` (headings), body `#2e2e33`, muted `#6b6b73`. No pure black/white text.
- Accent (one, used as a scale): indigo 600 `#4f46e5` main, 700 `#4338ca` hover, 50 `#eef2ff` tint.
- Semantic: pass green `#15803d` on `#dcfce7`; fail red `#b91c1c` on `#fee2e2`;
  can't test amber `#92400e` on `#fef3c7`; human/manual blue `#1d4ed8` on `#dbeafe`. All AA. Status is
  never colour alone: every pill has a word (and icon).
- Shadow: only on overlays (toasts, menus): `0 4px 12px rgba(20,20,30,.15)`. Cards use a border, not a shadow.
- Motion: 150ms press, 200ms hover/state, `cubic-bezier(0.25,1,0.5,1)`; animate only transform/opacity;
  respect `prefers-reduced-motion`.

## Classes
Layout: `.topbar` (app name left, user email + Log out right), `.container` (max-width 1080px, 16px side
padding on phones, 24px+ on desktop), `.page-head` (h1 + optional one-line subtitle + the one primary action),
`.stack` (vertical flow, 16px gap), `.stack-lg` (32px gap), `.row` (horizontal flex, 8px gap, wraps),
`.spacer` (flex:1), `.muted`, `.small` (13px), `.sr-only`.

Surfaces: `.card` (surface bg, 1px border, radius, 16–24px padding; never nest a card in a card),
`.section-title` (16px semibold).

Buttons (min height 44px, width ≈ 2× height padding): `.btn` base, `.btn-primary` (accent fill, only ONE per
screen section), `.btn-secondary` (surface + border), `.btn-ghost` (no bg until hover), `.btn-danger`
(red, for destructive only), `.btn-sm` (36px, for in-row actions), `.icon-btn` (44×44 square, needs
`aria-label` + `title`). States: hover, active (darker), `:focus-visible` ring (2px accent outline, 2px
offset), `:disabled` (50% opacity, not-allowed), `[aria-busy=true]`.

Forms: `.field` wraps `.label` (above input, always visible) + `.input` / `textarea.input` / `select.input` +
optional `.hint` (muted, 13px) + `.error-msg` (red, 13px). `.input.is-error` gets a red border.
`.checkbox` for a label wrapping an input[type=checkbox] (44px tall touch target).

Status pills (thin; vertical padding ¼–½ of horizontal): `.pill` + one of `.pill-pass` ("Pass", check icon),
`.pill-fail` ("Fail", x icon), `.pill-cant` ("Can't test", ban icon), `.pill-human` ("Needs a look", eye icon),
`.pill-fixed` (green, "Fixed"), `.pill-broke` (red, "Broke"), `.pill-same` (neutral, "Same"),
`.pill-neutral` (grey; for "Suggested", "Priority" uses `.pill-priority` = accent tint + flag icon,
"Approved" uses `.pill-pass`).

Table: `.table-wrap` (overflow-x auto on phones) > `table.table` (thead muted 13px, rows separated by
spacing/hairline, cells 12px 16px padding, `vertical-align: top`). On ≤640px, `table.table.stack-mobile`
turns each row into a block with `td[data-label]::before { content: attr(data-label) }` labels.

Feedback: `.spinner` (16px ring, spins), `.skeleton` (grey shimmer block for loading), `.empty`
(centered block: icon, one-line title, one-line help, one action), `.banner` + `.banner-error` /
`.banner-info` / `.banner-success` (inline message box with icon), `.toasts` / `.toast` / `.toast-success` /
`.toast-error` / `.toast-info` / `.toast-out` (bottom-right on desktop, bottom full-width on phones;
created by `EC.toast`).

Modal (only if needed): `.modal-backdrop` > `.modal` (max-width 520px, 24px padding, title, body,
right-aligned actions: Cancel `.btn-ghost` + one primary).

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
  `/run.html?id=…` (results of one run). Topbar on logged-in pages: "Eval Co-pilot" (link to /home.html),
  the user's email (muted, hidden on phones), "Log out" ghost button.

## Copy
Plain words, no jargon: say "link" not "URL", "check" not "assertion", "phone" / "laptop" not "device / UA".
Friendly, short. Example: "The site blocked us, so we can't test this."
