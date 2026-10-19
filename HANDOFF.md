# Handoff: finish Eval Co-pilot from the owner's laptop

Read `BUILD_PROMPT.md` first (the full spec), then this file. Everything below "Done" is built, committed
and pushed on branch `claude/relaxed-goldberg-svwx2h`. The build session ran in a cloud container whose
network blocked bublsolar.com, Groq, Supabase's API and *.vercel.app, and whose Vercel connector was
read-only. So **nothing has been deployed or tested live yet**. That is what's left.

## Done (in the cloud session)

- **Supabase** project "eval copilot", id `gryjkkvpeqzutwxfvedq`, URL `https://gryjkkvpeqzutwxfvedq.supabase.co`
  (org "adueumfkektbujyekurz"). Migrations applied: `init_eval_copilot` (= `db/supabase_setup.sql`),
  `lock_rls_auto_enable`, `fk_indexes` (files in `db/`). 8 tables, all with RLS. Security advisor clean
  except the expected `owns_project` note. The owner says "Confirm email" is turned off; verify it (step 3).
- **Two-user RLS test at the database level: passed on 16 points** (see `TESTING.md`).
- **All code:** 14 doors in `api/index.py` (+ `api/_lib/supa.py`, `groq.py`, `site.py`), 4 screens in
  `public/`, shared contract `docs/API.md`, UI kit `docs/UI_KIT.md`, design rules `docs/UIUX_RULES.md`
  (digest of github.com/stha-hardik/kole-uiux-skills). Unit tests: `python3 -m pytest -q tests/`.
- **Scripts:** `scripts/seed_bubl.py` (M3 data through the app's doors) and `scripts/smoke_live.py`
  (live M1/M2/M4/M5 checks). Both take passwords from the shell only.
- **Vercel:** the owner created project `eval-copilot` (team "stha-hardik's projects",
  `team_lciEz6VAmiLy7LQOp9umpVup`), linked to this GitHub repo, preset "Other". It has deployed `main` once
  (which only had the build prompt). **No env vars yet. Deployment protection still on.**

## Left to do, in order

1. **Get the code on the production branch.** The owner allows merging `claude/relaxed-goldberg-svwx2h`
   into `main` and pushing (a normal merge, no force-push), so every later push to `main` auto-deploys to
   production. Keep working on `main` afterwards.
2. **Vercel settings** (Vercel CLI as the owner: `npm i -g vercel`, `vercel login`, `vercel link` →
   team "stha-hardik's projects", project `eval-copilot`; or the Vercel connector if it has write access):
   - Env vars for Production + Preview + Development:
     `SUPABASE_URL=https://gryjkkvpeqzutwxfvedq.supabase.co`;
     `SUPABASE_ANON_KEY` = the legacy anon key (get it with the Supabase connector `get_publishable_keys`,
     or Supabase dashboard → Project Settings → API);
     `GROQ_API_KEY` = ask the owner to paste it in chat. Pipe it into `vercel env add` (e.g.
     `printf %s "$KEY" | vercel env add GROQ_API_KEY production`). Never echo it, never write it to a
     file, never commit it.
   - Turn off Vercel Authentication (Deployment Protection) so the link is public:
     `vercel api /v9/projects/eval-copilot --method PATCH` with body `{"ssoProtection": null}`,
     or Dashboard → Settings → Deployment Protection.
   - If pages 404 after deploy: Settings → Build and Output → Output Directory = `public`.
   - Redeploy (push to `main`, or `vercel --prod`). **Test `https://<prod-domain>/api/health` → `{"ok":true}`.**
3. **M2 live:** `python3 scripts/smoke_live.py https://<prod-domain>` (without EC_EMAIL it stops after the
   M2 part). It creates `tester.a+eval@example.com` / `tester.b+eval@example.com` with random passwords
   and checks that B gets an empty list and a 404. If sign-up says "check your email", "Confirm email" is
   still on: remind the owner once (Supabase → Authentication → Sign In / Providers → Email → off).
   Add the output to `TESTING.md` (M2 live section).
4. **The owner's account:** email `shresthahardik8@gmail.com`. Make a strong random password
   (`python3 -c "import secrets;print(secrets.token_urlsafe(16))"`), sign up through `/api/signup`, and tell
   the owner the password **in chat only**.
5. **M3 Brajesh's data:** `EC_EMAIL=… EC_PASSWORD=… python3 scripts/seed_bubl.py https://<prod-domain>`.
   It reads bublsolar.com's `/products.json` + `/collections.json` for the real Solaris / Walkie /
   Cabinet Lights handles, uses Tidy with AI for each pair's checks, saves all 10 approved, #8 priority.
   Then open the project page in a browser (Claude in Chrome if available) and sanity-check the pairs and
   checks; fix any wrong request link with Edit. (Checks lock once a pair has run, so fix before M4.)
6. **M4 + M5:** `EC_EMAIL=… EC_PASSWORD=… python3 scripts/smoke_live.py https://<prod-domain>`: Run 1 of
   all 10, a "changed" re-run of 2 pairs, Run 1 untouched, compare. ALSO do one real run through the UI in a
   browser: Run all → table fills live → 3 key points → answer one manual check → tick 2 pairs + type an
   "Other changes" note → Turn into a check → Re-run changed → "Good now?" panel → Compare. Check phone width
   too. Copy the Run 1 numbers (pass / fail / can't test, the 3 worst) into `REPORT.md`.
   If any pair times out (door 9 has a 50 s budget), check Vercel runtime logs.
7. **M6 polish:** check every screen against `docs/UIUX_RULES.md` once more in a real browser (Lucide icons
   and the Inter font were never seen rendered, because the CDN was blocked in the cloud), and check friendly
   error text, loading and empty states. Update `README.md`'s live link.
8. **`REPORT.md`** per BUILD_PROMPT section 11: live + repo links, what works per milestone and how it was
   tested, the RLS two-user result (database level from `TESTING.md` + live), the Bubl Solar Run 1 summary,
   anything the owner must do by hand, decisions from `DECISIONS.md`. Commit + push after each milestone.

## Rules that still apply
Opus plans/reviews; Sonnet/Haiku sub-agents for hands-on pieces; one owner per file; only the lead commits,
pushes, touches Supabase/Vercel or handles the Groq key. No service-role key. Never update or delete old runs
or results. Plain words on screen.
