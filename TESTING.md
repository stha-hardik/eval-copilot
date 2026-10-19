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

## M3 live: Bubl Solar seeded (19 Oct 2026)

`scripts/seed_bubl.py` (as the owner's account) read bublsolar.com's public product list, found the real
handles (`solaris`, `walkie`, collection `cabinet-lights`, colours Black / Rust Red / Sand), and saved the 10
pairs through doors 3, 4 (Tidy with AI) and 6, all approved, #8 priority. Before any run, the lead compared
every proposed check with the live pages and fixed four that could never give a true answer (DECISIONS 24).

## M4 + M5 live by script (Run 1 and Run 2)

`scripts/smoke_live.py` as the owner:

```
M4 Run 1: 20 rows · pass 20 · fail 0 · can't test 0
   manual checks waiting for 'Looks right / Looks wrong': 14
M5 Run 2 (changed): 4 rows; Run 1 untouched: True
   #8 good now? yes (phone pass, laptop pass)
   #1 good now? yes (phone pass, laptop pass)
   compare: {"same": 4}
```

Looking at the details found two real bugs, fixed and covered by new tests (DECISIONS 26, 27): Shopify's
hidden "sold out" labels were read as visible text (the AI wrongly said Sand and Rust Red were sold out),
and one AI check (#10 phone) said "AI could not judge" because Groq's free plan rate limit hit both tries.

## M4 + M5 live through the real screens (Run 3 and Run 4, Claude in Chrome)

Logged in as the owner (the owner typed the password; Claude never types passwords into a live site).

| Step | Result |
|---|---|
| Golden tests → **Run all approved pairs (10)** | Run 3 page opens; rows fill in pair by pair, progress bar moves, "running N of 10…" |
| Run 3 finished | **18 of 20 passed, 2 fail, 0 can't test**; 14 manual checks show **Looks right / Looks wrong** |
| 3 key points | 2 points (both #6, phone + laptop): "only the Black colour shows a price…" |
| Answer a manual check (#2 phone, verified first: the Solaris result links to `/products/solaris`, 200) | "Thanks — saved."; row shows 4 of 4 checks passed |
| Tick #6 and #8, type an "Other changes" note, **Turn into a check** | 1st proposal opened `/products/solaris-black` (does not exist), so it was **Discarded**; reworded note → proposal `GET /products/solaris` with Black / Sand / Rust Red / Add to cart checks → **Approve and include** (pair #11) |
| **Re-run changed** | Run 4: 3 pairs, 6 rows, **4 of 6 passed**. "Good now?" #6 **No** (nothing on the real site changed), #8 **Yes**, #11 **Yes** |
| Compare Run 4 with Run 3 | 0 fixed · 0 broke · 6 same (#11 "Not tested" in Run 3) |
| Run 1 rows after Runs 2–4 | unchanged (results are insert-only) |

The automatic compare at the end of Run 4 once showed "We couldn't reach the server" (the request never
reached the server); pressing Compare worked. It now retries once on a dropped connection.

## Redesign + phone and laptop check (M6b)

Every screen checked live at 1224px (laptop) and inside a 390px frame (phone; Chrome's window can't be
resized here): login, My projects, New project modal, Golden tests, Results (running and finished),
"Good now?" panel, Compare. Found and fixed on phones: nav crumbs cut off, tap targets under 44px
(nav pills, site chip, "More", banner link), a 130px sticky run bar (now 72px), "How to read this" filling
the first screen (now closed by default on phones), a lone nav pill cut off. After the fixes: no sideways
scroll on any screen (page width 375 = viewport), every button / link ≥ 44px tall (tick boxes sit in
44–75px tall labels).

## Secrets check (19 Oct 2026)

- Tracked files and the whole git history (all branches): 0 matches for `gsk_`, `sb_secret_`,
  `service_role`, `eyJhbGciOi` (JWT keys) or the owner's password.
- Live site: every page, script and stylesheet the browser can load has 0 matches for keys or the Supabase
  address; `/.env`, `/.env.local`, `/.vercel/project.json`, `/api/_lib/groq.py` → 404.
- The API without a login answers `{"detail":"Please log in."}` and never echoes settings.
- The Groq key and Supabase keys live only in Vercel's environment variables (encrypted). No `.env` file on
  disk; no copy of the key or password in project files, scratch files or shell history.

## M7: real browser (19 Oct 2026)

**Automated (no network):** `python3 -m pytest -q tests/` → **578 passed**. New files: `tests/test_browser.py`
(Browserless calls mocked: no key, bad key, busy twice → 1 retry after 5 s, out of units, down, timeout, payment /
login / captcha / forbidden-click hand-overs, budget too short; step validation incl. refused clicks),
`tests/test_m7_groq.py` (vision judge: model, JPEG data URL, ask again when unsure, unsure twice → a person),
`tests/test_m7_api.py` (routing per check, one session per pair + device, phone then laptop never at once, one
screenshot shared, the 12-session cap, the thin-page fallback, blocked pages, re-run of one pair, Run 1 untouched).
They found 8 bugs, all fixed (DECISIONS 41).

**Real site, local Chrome (GitHub Actions runner, same code Browserless runs, 0 units):**
`scripts/live/fn_harness.mjs` on bublsolar.com:

| Case | Result |
|---|---|
| #1 phone: open `/`, click the menu | menu opened (categories, search, cart visible); laptop: no menu button, step skipped |
| #6 open Solaris, click Sand | Sand selected, photo turned Sand, price ₹1,970 shown (Black is ₹1,680) |
| #7 click Turn On | lamp lit, button now "Turn Off" |
| #8 click Add to cart once (phone + laptop) | cart `item_count` 1: Solaris, Black, quantity 1 |
| #10 add, then `/checkout` | reached Shopify checkout → stopped: **payment** (nothing typed) |
| click "Buy it now" | refused: "could pay or place an order" |
| "Spin & Win" pop-up | closed automatically before clicks |
| Sessions | 3–14 s each (under 30 s = 1 Browserless unit each) |

Clicking the cart page's "Check out" button did nothing in an automated browser (no request, no new page), so #10's
steps open Shopify's `/checkout` directly.

**Live app (https://eval-copilot.vercel.app), throwaway account, exact copy of the owner's 10 Bubl pairs**
(`scripts/live/m7_live.py`, run from GitHub Actions):

```
health: {'ok': True, 'browser': False}   ← no Browserless token on Production (see REPORT)
Run 1: 20 rows · pass 19 · fail 1 · can't test 0 · via {'human': 10, 'fetch': 10}
  #2 #3 #4 #5 #9 → via fetch (plain page read)
  #1 #6 #7 #8 #10 → via human, browser checks passed=null,
      why "The real browser isn't set up, a person needs to check this"; no "Real browser" note claimed
Run 2 (re-run changed, #8 only): 2 rows; Run 1 untouched: True; #8 good now? yes
RESULT: PASS   (0 Browserless units used: no browser could open)
```
