# Testing

## M1: database + skeleton

- Applied `db/supabase_setup.sql` as migration `init_eval_copilot` with the Supabase connector.
- Checked with the connector: all 8 tables exist (`projects`, `golden_pairs`, `checks`, `runs`, `results`,
  `result_checks`, `changes`, `diagnosis_points`) and every one has RLS enabled (1–3 rules each).
- Security advisor: only the expected note about `owns_project` (SECURITY DEFINER, intentional) is left.
  It also flagged Supabase's own `rls_auto_enable()` helper; fixed by revoking API access
  (migration `lock_rls_auto_enable`).
- `/api/health` returns `{"ok": true}` locally (FastAPI test client).

## M2: RLS proven with two users (database level)

**How:** one SQL block run through the Supabase connector. It creates two throwaway users A and B,
then acts as each of them exactly the way the app does (role `authenticated` + the user's id in the
token claims, so every RLS rule applies). It ends by raising its own report as an error, which rolls
everything back. Nothing was left in the database (checked afterwards: 0 users, 0 projects, 0 results).

**Steps and results (19 Oct 2026):**

| # | Step | Result |
|---|---|---|
| 1 | A creates a project, pair, check, run, result, manual result check; A lists projects | A sees **1** |
| 2 | A tries to change Run 1's result from fail to pass | still **fail** (results can't be updated) |
| 3 | A tries to delete that result | **1** result left (results can't be deleted) |
| 4 | A tries to delete the run | **1** run left (runs can't be deleted) |
| 5 | A inserts a second result for the same run + pair + device | **refused** (no duplicates) |
| 6 | A adds a 4th worst-fail point to a run | **refused** (max 3) |
| 7 | B lists projects | **0** (empty list) |
| 8 | B asks for A's project by its id | **0** rows → the app answers **404** |
| 9 | B counts pairs / checks / runs / results / result checks / points | **0/0/0/0/0/0** |
| 10 | B adds a pair to A's project | **refused** |
| 11 | B creates a project owned by A | **refused** |
| 12 | After B tries to rename A's project | name still **"A site"** |
| 13 | After B tries to answer A's manual check | still **null** (waiting for A) |
| 14 | A answers the manual check "looks right" | **true** |
| 15 | A tries to change that answer again | still **true** (answered once) |
| 16 | A logged-out visitor reads projects | **refused** |

## M1 + M2 live (19 Oct 2026, https://eval-copilot.vercel.app)

- Vercel: 3 env vars set for Production, Preview and Development; Vercel Authentication turned off so the
  link is public; `main` deployed from GitHub.
- `GET /api/health` → `{"ok": true}`. `/`, `/home.html`, `/project.html`, `/run.html`, `/css/app.css` → 200.
- "Confirm email" is off: Supabase's `/auth/v1/settings` reports `mailer_autoconfirm: true`, and sign-up
  returns a session straight away.
- Two-user test through the live app's own doors (`python3 scripts/smoke_live.py https://eval-copilot.vercel.app`,
  random passwords, nothing written to a file):

```
M1 health: {'ok': True}
M2 RLS: A=tester.a+eval@example.com sees 1 project(s); B=tester.b+eval@example.com sees 0; B asking for A's project by id -> 404
```

- The owner's account was created through `/api/signup` and logs in through `/api/login` (200).

## Automated tests (no network needed)

`python3 -m pytest -q tests/`:
- `tests/test_groq.py`: AI helper: JSON parsing, one retry, safe cleaning of AI output (no other hosts,
  valid rules only), the "AI could not judge, please look" fallback.
- `tests/test_site.py`: reading the site: phone/laptop requests, bot-block detection, timeouts, the Shopify
  cart flow (variant lookup → add → read cart), every code check.
- `tests/test_api.py`: every door end to end against an in-memory stand-in for Supabase that enforces the
  same rules, with a scripted fake site that can be "broken" then "fixed".
