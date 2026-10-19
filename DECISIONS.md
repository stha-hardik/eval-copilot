# Decisions I made on my own

1. **Supabase project.** The project is named "eval copilot" (id `gryjkkvpeqzutwxfvedq`, region ap-south-1).
2. **Security advisor fix.** The advisor flagged `public.rls_auto_enable()`, a Supabase-created event-trigger
   helper (it turns RLS on for every new table). Signed-in and signed-out users could call it over the API.
   Event triggers don't need EXECUTE grants, so I revoked them (migration `lock_rls_auto_enable`,
   `db/migration_02_lock_rls_auto_enable.sql`). The `owns_project` note is expected and left alone.
3. **Performance advisor fix.** Added 3 indexes on pointers that had none (migration `fk_indexes`,
   `db/migration_03_fk_indexes.sql`). Speed only, no change to data or rules.
4. **Network workaround.** This build container's network blocks bublsolar.com, api.groq.com, *.vercel.app
   and *.supabase.co. So I talk to Supabase through the connector, and I test the live app from a
   Vercel Sandbox (which has open internet) instead of from my own shell. The Groq key is never in a
   file: it only goes into Vercel's environment variables.
5. **`requests` only for Supabase too.** The server talks to Supabase's REST and Auth APIs with plain
   `requests` (no supabase SDK), passing the user's access token so RLS always applies.
6. **Vercel project created by hand.** The Vercel connector in the build session could only read, not
   create projects or set env vars, so the owner created the `eval-copilot` project in the dashboard.
   Env vars, deployment protection and the production branch are set in the laptop session.
7. **One Groq call per device instead of one per check.** "Judge one check" (job 3) is batched: one call
   answers all AI checks of a pair on one device and writes the one-line why for every failed code check.
   Phone and laptop run in parallel. This keeps each pair well under Vercel's 60-second limit.
8. **Time budget.** Door 9 gives itself 50 s: site requests time out at 15 s, the AI gets what is left. If
   the AI runs out of time, AI checks are saved as "AI could not judge, please look" (passed = null).
9. **The why for every fail is stored on the check** (`result_checks.why`), because `results` has no why
   column. The row's one-line why is the first failed check's why.
10. **Outcome rules in detail.** Blocked (403/429/challenge page) → can't test, every check saved as
    "The site blocked us, so we can't test this." Page didn't load (4xx/5xx/timeout) → fail: the status
    check carries the reason, other automatic checks say "Not checked, because the page didn't load",
    manual checks still wait for a human. Otherwise: any check false → fail; at least one true → pass;
    nothing decided (all manual, or the AI couldn't judge) → can't test.
11. **Bot-block detection is careful on 200 pages.** Shops often load a captcha script on normal pages, so a
    200 reply only counts as blocked when it is a short page with a real challenge marker
    (Cloudflare "Just a moment…"). 403 and 429 always count as blocked.
12. **Shopify cart pairs.** A pair that POSTs to `/cart/...` runs in its own session per device (so the cart
    starts empty), finds the variant id from `/products/<handle>.json` when the pair names a handle and
    colour, adds it, then reads `/cart.js`; the checks run against that cart.
13. **Checks lock after a pair has run.** Old results point at their checks, and deleting a check would
    delete old result rows (breaking "never change old runs"). So a pair's checks can be edited until it has
    run once; after that the screen shows "Checks are locked after a run" and the builder adds a new pair.
14. **3 worst fails, exact order.** Priority first, then failed on both devices, then by position. Different
    pairs come before the second device of the same pair, so the 3 points cover 3 problems when possible.
15. **Compare.** With `?with=<run>` it compares with that run; without, each pair is compared with the most
    recent earlier run that tested it. "Good now?" = yes only when the pair passes on both phone and laptop.
16. **Ticked pairs are saved as changes** with the note "Ticked as changed"; the "Other changes" note is
    saved on the new pair the AI made from it (or with no pair if the builder didn't approve one).
17. **"Other changes" uses its own AI job** (job 5, `change_to_pair`) through door 4 with `kind: "change"`,
    so door 4 stays the one tidy door the spec lists.
18. **Public links only.** New sites must be http(s) links with a dot in the name, no username/password in
    the link, and no local or private addresses.
19. **Design.** Followed the owner's Kole UI/UX skill (`docs/UIUX_RULES.md`): Inter (2 weights), one indigo
    accent, neutral greys, 4/8 px spacing, borders not shadows, status always a word + icon + colour,
    Lucide icons, real loading/empty/error/success states, light and dark mode. No sidebar: the app has
    3 screens, so a top bar is enough.
20. **Seed and smoke scripts.** `scripts/seed_bubl.py` enters Brajesh's 10 pairs through the app's own doors
    (Tidy with AI proposes the checks; real handles are read from bublsolar.com's public product list).
    `scripts/smoke_live.py` repeats the two-user RLS test and the run / re-run / compare checks against the
    live app. Passwords come from the shell, never from a file.
21. **Bugs found by the end-to-end tests, fixed.** Local/private links in any spelling (127.1, 0x7f.0.0.1,
    localhost., *.localhost) are refused when a site is added, and the site reader re-checks every address
    (including every redirect hop) so a public link can't bounce us into a private network. Malformed links
    and ids answer 400/404 instead of 500. The row's one-line why is always the real reason. The "Good now?"
    panel names each pair even before it has run. A "changed" run only runs the pairs it was started with.
22. **Schema change: `checks.created_at` and `changes.created_at` default to `clock_timestamp()`**
    (migration `ordered_created_at`, `db/migration_04_ordered_created_at.sql`). Postgres gives every row of one
    insert the same `now()`, so a pair's checks could come back shuffled; now they keep the order they were
    written in.
23. **A human's "Looks right / Looks wrong" answer is saved on the check, not on the result.** Results can
    never be changed (that's what keeps Run 1 honest), so the row's outcome stays what the run decided and
    the screen shows the human's answer next to it.
24. **Fixed four of the AI-proposed checks before Run 1** (checks lock once a pair has run). Seeded with
    Tidy with AI on 19 Oct 2026, then compared with the live pages: #8 had `text_absent "5"`, which always
    fails on Shopify's cart reply (prices and ids contain 5s), so it became "exactly 1 item, 1 line, colour
    Black". #10's `text_has "Shipping"` / `"discount"` always passed because the cart reply has
    `requires_shipping` / `total_discount` fields, so they became an AI check on the cart plus a manual
    checkout check (the checkout page can't be reached without a browser). #5 and #6 looked for phrases the
    page never uses ("charging options", "price", "availability"), so they now look for the page's real
    headings (Dimensions, Lumen, Charging time, Runtime, Warranty) and ask the AI the rest.
25. **Local tests need Python 3.10+.** The code uses `X | None` type hints (Vercel runs Python 3.12). On a
    Mac whose `python3` is 3.9, make a 3.12 venv first (e.g. `uv venv --python 3.12`).
26. **Hidden Shopify "sold out" labels are ignored when reading a page.** Shopify's Dawn theme puts a hidden
    "Variant sold out or unavailable" label on every colour and only shows it (with CSS) when that colour
    really is sold out. The page reader kept it, so in Run 1 the AI said Sand and Rust Red were sold out
    when all three colours were in stock. The reader now drops `label-unavailable` elements.
27. **Waiting when Groq says "too many requests".** The free Groq plan allows about 8,000 tokens a minute.
    In Run 1 one AI check (#10 phone) came back "AI could not judge" because both tries hit that limit
    back to back. On a 429 the server now waits as long as Groq asks (inside the time budget) before
    the retry.
28. **Redesign to the owner's "Tactile Calm" mockups (19 Oct 2026).** The owner sent Stitch mockups (PNG +
    HTML) for every screen and asked for motion from their kole-uiux-skills animation rules. We kept the look
    (soft raised / pressed surfaces on one chalk-blue base, Plus Jakarta Sans, sage / terracotta / amber
    status colours) but translated it to plain CSS (no Tailwind CDN, no Material Symbols: Lucide stays the
    one icon set). Mockup decoration with no real feature behind it was left out (e.g. "Forgot?",
    "All systems operational", "Overall health 92.5%", staging server log, "Download diff log") because the
    build rules forbid invented features and made-up numbers. The accent was deepened from `#5B7FAE` to
    `#4E72A1` so white button text passes AA contrast. Light theme only, as in the mockups. Motion:
    transform/opacity only, ease-out curves, one signature moment per screen (results rows slide in and
    their status pops as each pair finishes), and `prefers-reduced-motion` turns it all off. The old
    `docs/UIUX_RULES.md` digest is superseded by `docs/REDESIGN.md` where they differ.
29. **One component system (19 Oct 2026).** Every repeated control is defined once in `app.css` (look +
    motion) and, when it needs behaviour, once in `public/js/ui.js` (`EC.ui.*`): top bar + tabs, segmented
    control with a sliding indicator, switch, icon toggle, checkbox, disclosure, menu, pill, stat tile,
    project card. Spec: `docs/COMPONENTS.md`. The mockup's top-bar tabs, avatar and stat tiles are now built,
    but only from real data: tabs link to the current or last opened project / run (disabled until there is
    one), and the stats are sums of each project's last run. The mockup's "All systems operational" pill was
    left out at the owner's request: it could only say whether our own server answers, which a builder could
    misread as "your site is fine". On phones the tabs move to a bottom tab bar. The ring on the pass-rate tile is the one animation
    that is not transform/opacity (a tiny SVG stroke).

## M7: real browser replaces human checks (19 Oct 2026)

30. **Browserless through its Function API, from Python with `requests`.** `api/_lib/browser.py` posts
    `api/_lib/browser_fn.mjs` (Puppeteer) to `https://production-sfo.browserless.io/function` with the steps as
    `context`. One HTTP call = one session, so the whole multi-step flow (open, click, read the cart, one screenshot)
    runs in one browser with no Playwright or Chromium on Vercel. Session timeout 45 s, ads/fonts/media blocked,
    images only when a screenshot is needed.
31. **Finding the token.** The build session could not list Vercel env var names (the connector is read-only), so
    the server reads `BROWSERLESS_TOKEN`, else any variable with BROWSERLESS in its name, else one with BROWSER and
    TOKEN/KEY. `/api/health` reports only `browser: true/false`.
32. **One session per pair + device uses the first browser check's steps.** All browser checks of a pair share that
    session and its one screenshot (the owner's rule), so a pair's browser checks should share the same steps.
33. **The safety guard runs after every step,** not only at the end: payment pages (Shopify `/checkouts`, card
    fields, or a big frame from a one-click checkout provider such as GoKwik / Shiprocket / Razorpay), login pages
    (password or OTP fields, `/account/login`) and bot checks stop the session and hand the check to a person.
    Clicks on pay / place order / buy it now / log in / sign up / subscribe / "spin" are refused, both when a pair is
    saved (400) and in the browser. The browser never types anything.
34. **Marketing pop-ups are closed like a shopper would** (their close button, else hidden). bublsolar.com shows a
    "Spin & Win" pop-up that covered the colour swatches and blocked clicks. A pop-up that holds a frame is left
    alone, because it may be a checkout.
35. **Longer function time.** Two browser sessions one after the other (phone, then laptop) plus the AI can take
    over 60 s, so `vercel.json` gives `api/index.py` 150 s (Fluid compute; the deploy accepted it). Door 9 keeps
    30 s for the AI; a laptop session that would not fit is handed to a person with the reason.
36. **#2, #4 and #9 keep plain page reads.** Their manual checks became `ai_judge` questions on the page text
    (search result listed, prices listed, cart contents), as the owner's spec says those pairs stay fetch.
    #8 changed its own request from the cart API to the product page, because the real click now adds to the cart.
37. **Manual checks were converted in place.** Old results keep their answers; on old runs those checks now show
    the new rule's tag. Deleting the old checks would have deleted old results, which is never allowed.
38. **Vision model:** Groq `meta-llama/llama-4-scout-17b-16e-instruct` (Groq's vision docs), JPEG at quality 55
    (about 15–55 KB, far under Groq's 4 MB base64 limit), JSON `{passed, why, confident}`. Not confident → ask again
    once for just those checks → still not confident → a person.
39. **The cap counts results with `via` browser or human in the run** (each is one session or a refused one), so a
    re-run of one pair uses at most 2 sessions and a full Bubl run uses 10 of the 12 allowed.
40. **Live tests used a throwaway test account with an exact copy of the owner's Bubl Solar pairs.** The build
    session can't log in as the owner (it never has the password), so a GitHub Actions runner signed up a test
    account through the app, copied the 10 pairs exactly as stored, and ran them on the live link. The owner's own
    project has the same checks and runs the same way from "Run all".
