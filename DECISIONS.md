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
