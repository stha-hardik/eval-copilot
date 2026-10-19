# Eval Co-pilot: audit before check-in 5 (20 Oct 2026)

Live app: https://eval-copilot.vercel.app · Repo: https://github.com/stha-hardik/eval-copilot (public) ·
Audited commit: `main` (see section 7) · Automated tests: **591 passed**.

## 1. Summary

**Ready for a user test, with one condition.** Every screen and door works on the live link, privacy holds
(**93 of 93** two-user probes passed, on the app's doors and directly on Supabase), Run 1 is never overwritten,
and the core promise works on both kinds of target: a shop (Bubl Solar, real Chrome clicks + screenshots) and an
**AI feature** (a demo assistant with a planted flaw: Run 1 caught it, the prompt was fixed, Re-run changed showed
**FIXED** and "Good now? yes", Run 1 untouched). The condition: Groq's free plan allows **200,000 tokens a day** for
its image model, about **5–6 full Bubl runs with screenshot answers per day**; after that, screenshot checks say
"The AI was busy (too many requests), a person needs to check this".

**Three biggest risks**
1. **Groq free-plan daily cap on screenshots** (see above). Today's testing used it up; it refills over 24 hours.
   Fix: Groq Dev Tier (paid) before the user test, or keep to ~4 full runs that day.
2. **A person's "Looks wrong" never becomes a fail.** Results are insert-only (by design, so Run 1 can't be
   overwritten), so a human answer is saved on the check but does not change the row's outcome, the pass count,
   the 3 worst, Compare or "Good now?". Needs a design decision (section 8).
3. **No usage limits on the server.** Sign-up is open and every account can spend Groq tokens and Browserless units;
   the demo AI endpoint is public too (capped input, short answers). Fine for a hackathon, not for strangers at scale.

## 2. Inventory: what's been built

**Links:** live app https://eval-copilot.vercel.app (latest production deploy Ready, `/api/health` →
`{"ok":true,"browser":true}`); repo public on GitHub.

**Screens (5 pages)**

| Page | What it does |
|---|---|
| Landing `/` | Public page explaining the app; "Dashboard" when logged in, "Log in / Sign up" when not. |
| Log in / Sign up `/login`, `/signup` | One page, two tabs, show/hide password; after login → dashboard (or back to the page you came from). |
| My projects `/home.html` | Your sites only, each with last run, pass count, date, status and progress bar; 3 real stat tiles; New project pop-up (public link only). No ranking. |
| Golden tests `/project.html?id=` | Example pair, type or speak (mic) a rough pair, **Tidy with AI**, **Suggest pairs** (marked "suggested"), edit / approve / priority, how each check is done (Code / AI / Real browser / You check), **Run all approved pairs**. |
| Results `/run.html?id=` | Fills in live pair by pair (phone + laptop); "How to read this" key; rows priority-first then fails; "Looks right / Looks wrong" for human checks; **3 things to fix first**; **Re-run changed** (tick boxes + "Other changes" → AI turns it into a check to approve); after a re-run the **"Good now? yes / no"** panel; **Compare** with any earlier run (FIXED / BROKE / same). |

Shared: one component system (`public/css/app.css` + `public/js/ui.js`): top bar with tabs (bottom tab bar on
phones), avatar menu with dark-theme switch, switch / star / tick box / segmented control / disclosure / menu / pill.

**API doors** (`api/index.py`): all 14 spec doors present, no missing ones.

| Spec door | Status | Note |
|---|---|---|
| 1 signup / login, 1b refresh | present | signup 409 only if "Confirm email" is on (it's off) |
| 2 / 2b projects | present | 2b adds `has_results` per pair |
| 3 create project | present | refuses non-links, private / local addresses |
| 4 tidy | present | also `kind:"change"` = Groq job 5 (Other changes) |
| 5 suggestions | present | up to 5 drafts |
| 6 create pair / 7 edit pair | present | checks may carry browser `steps`; checks lock once a pair has run (409) |
| 8 create run | different (small) | extra `other_pair_id`; replies `{run, pair_ids}` |
| 9 run one pair | present | idempotent; fetch → real browser → person |
| 10 finish / 11 read run | present | 11 adds `project`, `earlier_runs` |
| 12 compare | different (small) | `?with=` optional |
| 13 human answer | present | only while the check is blank; 409 after |
| 14 health | different (small) | adds `browser: true/false` (never the key) |
| extra | `POST /api/demo-ai/answer` | **demo only** for this audit (section 5), clearly separated in `api/_lib/demo_ai.py` |

Only health, signup, login, refresh and the demo need no login.

**Groq jobs** (`api/_lib/groq.py`, text model `openai/gpt-oss-120b`): job 1 tidy a pair, job 2 suggest pairs,
job 3 judge AI checks + write the why for failed code checks (one call per pair per device), job 4 explain the
3 worst, job 5 "other changes" → a pair. Vision: `judge_screenshot` with **`qwen/qwen3.8-27b`** (Groq retired Llama 4
Scout; found and fixed today), sends a before + after screenshot when the check clicked something. Demo app only:
`openai/gpt-oss-20b`. All JSON-mode, retried, rate-limit aware; failures become "AI could not judge, please look".

**Browserless** (`api/_lib/browser.py` + `browser_fn.mjs`): one call type, `POST
https://production-sfo.browserless.io/function` (token from the `BROWSERLESS_TOKEN` env var, never logged). Real Chrome
as a phone (390×844) and a laptop (1440×900), phone then laptop, at most 12 sessions per run, 45 s per session.
Steps: open, click, wait, scroll. **Owner's rule (new today): only one page + at most one click**; longer flows are
checked by code + AI on the fetched page. Never types, pays, logs in or signs up; stops by itself on payment, login
or captcha pages and hands the check to a person with the reason. Screenshots live in memory only, never stored.

**Database** (read live with the Supabase connector): 8 tables (`projects`, `golden_pairs`, `checks`, `runs`,
`results`, `result_checks`, `changes`, `diagnosis_points`), RLS on all 8. Live migrations: `init_eval_copilot`,
`lock_rls_auto_enable`, `fk_indexes`, `ordered_created_at`, `m7_real_browser`, `projects_policy_initplan` (new, audit
fix) = `db/supabase_setup.sql` + `db/migration_02…06`. **No drift** between files and the live schema. Key rules
seen live: `results` has select + insert policies only (no update / delete), unique (run, pair, device);
`result_checks` update only where `passed is null`; `diagnosis_points` rank 1–3 + unique (run, rank); `runs` unique
(project, run_number), no delete policy; every child table's policies go through `owns_project()`.

**Milestones**

| Milestone | Status |
|---|---|
| M1 skeleton, database, deploy | done |
| M2 login, projects, RLS proven | done (re-proven today, 93/93) |
| M3 golden pairs + Brajesh's data | done (Bubl Solar, 12 pairs: old #10 switched off, #12 replaces it) |
| M4 run | done |
| M5 re-run changed + compare | done |
| M6 polish + docs (+ Tactile Calm redesign, components) | done |
| M7 real browser (Browserless) | done, live, with today's fixes |
| Wording update (Code / AI / Real browser / You check) | done |
| Landing page (+ dark theme) | done |

## 3. Security and row-level security

Two fresh accounts (A, B) made through the live sign-up; A created a project, a pair (code + manual checks), a full
run and a "changed" run, so A had rows in **all 8 tables** (including `changes` and 2 `diagnosis_points`). Then B, a
logged-out caller (anon key only) and A attacked: through the app's doors and directly on Supabase REST
(`/rest/v1/<table>` with B's token / the anon key). Test data is labelled **"AUDIT TEST (safe to delete)"**, accounts
`audit.a+992622@example.com` and `audit.b+511248@example.com`.

**Result: 93 probes, 93 PASS, 0 FAIL.**

| Table | Action | User | Expected | Actual | Result |
|---|---|---|---|---|---|
| projects | select A's row (REST) | B | 0 rows | 200 0 | PASS |
| projects | update A's row (REST) | B | 0 rows changed | 200 0 | PASS |
| projects | delete A's row (REST) | B | 0 rows deleted | 200 0 | PASS |
| projects | select A's row (REST) | logged out | 0 rows | 401 {'code': '42501', 'details': None, 'hint': 'Grant the required privileges to the current role with: GRANT SELECT ON public.projects TO anon;', 'message': 'permission denied for table projects'} | PASS |
| projects | update A's row (REST) | logged out | 0 rows changed | 401 refused | PASS |
| projects | delete A's row (REST) | logged out | 0 rows deleted | 401 refused | PASS |
| golden_pairs | select A's row (REST) | B | 0 rows | 200 0 | PASS |
| golden_pairs | update A's row (REST) | B | 0 rows changed | 200 0 | PASS |
| golden_pairs | delete A's row (REST) | B | 0 rows deleted | 200 0 | PASS |
| golden_pairs | select A's row (REST) | logged out | 0 rows | 401 {'code': '42501', 'details': None, 'hint': 'Grant the required privileges to the current role with: GRANT SELECT ON public.golden_pairs TO anon;', 'message': 'permission denied for table golden_pairs'} | PASS |
| golden_pairs | update A's row (REST) | logged out | 0 rows changed | 401 refused | PASS |
| golden_pairs | delete A's row (REST) | logged out | 0 rows deleted | 401 refused | PASS |
| checks | select A's row (REST) | B | 0 rows | 200 0 | PASS |
| checks | update A's row (REST) | B | 0 rows changed | 200 0 | PASS |
| checks | delete A's row (REST) | B | 0 rows deleted | 200 0 | PASS |
| checks | select A's row (REST) | logged out | 0 rows | 401 {'code': '42501', 'details': None, 'hint': 'Grant the required privileges to the current role with: GRANT SELECT ON public.checks TO anon;', 'message': 'permission denied for table checks'} | PASS |
| checks | update A's row (REST) | logged out | 0 rows changed | 401 refused | PASS |
| checks | delete A's row (REST) | logged out | 0 rows deleted | 401 refused | PASS |
| runs | select A's row (REST) | B | 0 rows | 200 0 | PASS |
| runs | update A's row (REST) | B | 0 rows changed | 200 0 | PASS |
| runs | delete A's row (REST) | B | 0 rows deleted | 200 0 | PASS |
| runs | select A's row (REST) | logged out | 0 rows | 401 {'code': '42501', 'details': None, 'hint': 'Grant the required privileges to the current role with: GRANT SELECT ON public.runs TO anon;', 'message': 'permission denied for table runs'} | PASS |
| runs | update A's row (REST) | logged out | 0 rows changed | 401 refused | PASS |
| runs | delete A's row (REST) | logged out | 0 rows deleted | 401 refused | PASS |
| results | select A's row (REST) | B | 0 rows | 200 0 | PASS |
| results | update A's row (REST) | B | 0 rows changed | 200 0 | PASS |
| results | delete A's row (REST) | B | 0 rows deleted | 200 0 | PASS |
| results | select A's row (REST) | logged out | 0 rows | 401 {'code': '42501', 'details': None, 'hint': 'Grant the required privileges to the current role with: GRANT SELECT ON public.results TO anon;', 'message': 'permission denied for table results'} | PASS |
| results | update A's row (REST) | logged out | 0 rows changed | 401 refused | PASS |
| results | delete A's row (REST) | logged out | 0 rows deleted | 401 refused | PASS |
| result_checks | select A's row (REST) | B | 0 rows | 200 0 | PASS |
| result_checks | update A's row (REST) | B | 0 rows changed | 200 0 | PASS |
| result_checks | delete A's row (REST) | B | 0 rows deleted | 200 0 | PASS |
| result_checks | select A's row (REST) | logged out | 0 rows | 401 {'code': '42501', 'details': None, 'hint': 'Grant the required privileges to the current role with: GRANT SELECT ON public.result_checks TO anon;', 'message': 'permission denied for table result_checks'} | PASS |
| result_checks | update A's row (REST) | logged out | 0 rows changed | 401 refused | PASS |
| result_checks | delete A's row (REST) | logged out | 0 rows deleted | 401 refused | PASS |
| changes | select A's row (REST) | B | 0 rows | 200 0 | PASS |
| changes | update A's row (REST) | B | 0 rows changed | 200 0 | PASS |
| changes | delete A's row (REST) | B | 0 rows deleted | 200 0 | PASS |
| changes | select A's row (REST) | logged out | 0 rows | 401 {'code': '42501', 'details': None, 'hint': 'Grant the required privileges to the current role with: GRANT SELECT ON public.changes TO anon;', 'message': 'permission denied for table changes'} | PASS |
| changes | update A's row (REST) | logged out | 0 rows changed | 401 refused | PASS |
| changes | delete A's row (REST) | logged out | 0 rows deleted | 401 refused | PASS |
| diagnosis_points | select A's row (REST) | B | 0 rows | 200 0 | PASS |
| diagnosis_points | update A's row (REST) | B | 0 rows changed | 200 0 | PASS |
| diagnosis_points | delete A's row (REST) | B | 0 rows deleted | 200 0 | PASS |
| diagnosis_points | select A's row (REST) | logged out | 0 rows | 401 {'code': '42501', 'details': None, 'hint': 'Grant the required privileges to the current role with: GRANT SELECT ON public.diagnosis_points TO anon;', 'message': 'permission denied for table diagnosis_points'} | PASS |
| diagnosis_points | update A's row (REST) | logged out | 0 rows changed | 401 refused | PASS |
| diagnosis_points | delete A's row (REST) | logged out | 0 rows deleted | 401 refused | PASS |
| projects | insert into A's data (REST) | B | refused | 403 | PASS |
| projects | insert into A's data (REST) | logged out | refused | 401 | PASS |
| golden_pairs | insert into A's data (REST) | B | refused | 403 | PASS |
| golden_pairs | insert into A's data (REST) | logged out | refused | 401 | PASS |
| checks | insert into A's data (REST) | B | refused | 403 | PASS |
| checks | insert into A's data (REST) | logged out | refused | 401 | PASS |
| runs | insert into A's data (REST) | B | refused | 403 | PASS |
| runs | insert into A's data (REST) | logged out | refused | 401 | PASS |
| results | insert into A's data (REST) | B | refused | 403 | PASS |
| results | insert into A's data (REST) | logged out | refused | 401 | PASS |
| result_checks | insert into A's data (REST) | B | refused | 403 | PASS |
| result_checks | insert into A's data (REST) | logged out | refused | 401 | PASS |
| changes | insert into A's data (REST) | B | refused | 403 | PASS |
| changes | insert into A's data (REST) | logged out | refused | 401 | PASS |
| diagnosis_points | insert into A's data (REST) | B | refused | 403 | PASS |
| diagnosis_points | insert into A's data (REST) | logged out | refused | 401 | PASS |
| (door) | GET /api/projects/{A project} | B | 404 | 404 | PASS |
| (door) | GET /api/runs/{A run} | B | 404 | 404 | PASS |
| (door) | GET /api/runs/{A run2}/compare | B | 404 | 404 | PASS |
| (door) | PATCH /api/pairs/{A pair} | B | 404 | 404 | PASS |
| (door) | POST /api/projects/{A project}/pairs | B | 404 | 404 | PASS |
| (door) | POST /api/projects/{A project}/runs | B | 404 | 404 | PASS |
| (door) | POST /api/runs/{A run}/pairs/{A pair} | B | 404 | 404 | PASS |
| (door) | POST /api/runs/{A run}/finish | B | 404 | 404 | PASS |
| (door) | PATCH /api/result-checks/{A check} | B | 404 | 404 | PASS |
| (door) | POST /api/projects/{A project}/suggestions | B | 404 | 404 | PASS |
| projects | list (door) | B | 0 of A's | 0 | PASS |
| (door) | GET projects | logged out | 401 | 401 | PASS |
| (door) | GET runs/f19f6e82-7b33-4 | logged out | 401 | 401 | PASS |
| (door) | POST pairs/tidy | logged out | 401 | 401 | PASS |
| results | insert A's pair into B's own run (REST) | B | refused | 403 | PASS |
| (door) | POST /api/runs/{B run}/pairs/{A pair} | B | 404 | 404 | PASS |
| (door) | re-run B's project with A's pair id | B | 400/404 | 400 | PASS |
| results | update own result (REST) | A | 0 rows changed | 200 0 | PASS |
| results | delete own result (REST) | A | 0 rows deleted | 200 0 | PASS |
| runs | delete own Run 1 (REST) | A | 0 rows deleted | 200 0 | PASS |
| results | duplicate run+pair+device (REST) | A | 409 refused | 409 | PASS |
| diagnosis_points | 4th point (rank 4) | A | refused | 400 | PASS |
| result_checks | change a decided check (REST) | A | 0 rows changed | 200 0 | PASS |
| result_checks | fill blank human check (door 13) | A | 200 | 200 | PASS |
| result_checks | answer it a second time (door 13) | A | 409 | 409 | PASS |
| results | Run 1 after re-run + all attacks | A | unchanged | unchanged | PASS |
| (auth) | refresh door with a good refresh token | A | 200 + new session | 200 | PASS |
| (auth) | door with an expired/bad token | anyone | 401 plain message | 401 {"detail": "Please log in again."} | PASS |
| (auth) | refresh with a bad refresh token | anyone | 401 | 401 | PASS |

**Also checked**
- **Secrets:** no key, token or password value in any tracked file or anywhere in git history (`gsk_`, `sb_secret_`,
  `service_role`, JWT `eyJhbGciOi…`, the Browserless token, the owner's password: 0 hits). Every file the live site
  serves (pages, scripts, styles) has 0 key hits; `/.env`, `/.env.local`, `/.vercel/project.json`,
  `/api/_lib/groq.py` → 404. The browser only ever gets the user's own session token.
- **Service-role key:** not used anywhere (no code reads it).
- **Supabase security advisor:** (1) `owns_project` is SECURITY DEFINER: expected and intentional; (2) **Leaked
  password protection is off**: a dashboard switch (Human to do). **Performance advisor:** (1) `projects` policy
  re-read `auth.uid()` per row → **fixed** (migration `projects_policy_initplan`); (2) one unused index
  (`diagnosis_points_result_id_idx`): kept (it backs a foreign key).
- **Session expiry:** `/api/refresh` with a good refresh token → 200 + new session; a bad or expired token → 401
  "Please log in again."; the browser calls refresh once on a 401 and retries.

## 4. Functional tests (live link)

| Feature | Result | Evidence |
|---|---|---|
| Pages load (`/`, `/login`, `/signup`, `/home.html`, `/project.html`, `/run.html`) | PASS | all 200 |
| Landing logged out / logged in, sign up → dashboard | PASS | earlier live check 52/52 (TESTING.md "Landing page"); log in → dashboard today |
| Create project; bad links refused | PASS | missing link → 400 "Please paste the link…"; "bubl solar" → 400; `127.0.0.1` and `10.0.0.5` → 400 "Please use the public link" |
| Wrong password | PASS | 401 "That email and password don't match." |
| Add a pair by typing / with Tidy with AI / edit / approve / priority | PASS | Demo AI project: 5 pairs saved through door 6; Bubl #12 through door 6; old #10 switched off through door 7 |
| Suggest pairs | PASS | door 5 tested end to end in the test suite; live earlier (TESTING.md) |
| Mic button | Human to do | needs a real microphone permission; the code hides the mic when the browser can't do speech |
| Full run fills in live, every row has an outcome | PASS | Run 12 Bubl: 22 rows, 20 pass / 2 fail / 0 can't test; seen filling live in Chrome on Run 3 and Run 9 |
| `via` correct (fetch / browser / human) | PASS | #1, #6, #7, #8 via real browser (`[browser] … browser opened yes · screenshots before+after`); others via page read; payment stops via human |
| 3 key points + "How to read this" | PASS | Run 12 points: #6 phone + laptop ("only the Black colour shows a price…"); key shows the 6 definitions |
| Re-run changed + Other changes → "Good now?" | PASS | Run 11 (Bubl #7, #8): good now yes / yes; Demo AI Run 3: yes / yes; Other changes → AI check → approve shown live in Run 4 (TESTING.md) |
| Run 1 untouched; compare FIXED / BROKE / same | PASS | Run 10 untouched after Run 11; compare Run 11 vs 10: 1 FIXED, 3 same; Demo AI Run 3 vs Run 1: 4 FIXED |
| Real browser: clicks, cart, framing, before/after | PASS | #8 cart = 1 Solaris Black on phone + laptop; #7 "lamp glowing, button now says Turn Off"; #6 "Color: Sand, sand lamp shown" |
| Real browser: sessions used | PASS | 8 sessions per full Bubl run (4 pairs × 2 devices), under the cap of 12 |
| Real browser fallback to a person | PASS | no key → "The real browser isn't set up…"; wrong key → "…didn't accept our key…"; payment page → "Payment page, a person needs to check this" |
| Site blocks us | PASS | a 403 / bot wall → "can't test" (not fail); unreachable site → "We couldn't reach the site." |
| Groq failing (simulated locally) | PASS | Tidy → "The AI didn't answer. Please try again."; judge → "AI could not judge, please look" |
| Groq busy | PASS (honest) | screenshot checks → "The AI was busy (too many requests), a person needs to check this" (Run 12) |
| Phone-sized screens | PASS | every page checked at 390 px earlier today (no sideways scroll, 44 px targets); landing 52/52 on phone size; results / Good now? / compare re-checked on phone |

Problems found while testing **and fixed today** (all re-tested live):
1. Groq had retired the vision model → every screenshot answer was "not sure" (fixed: `qwen/qwen3.8-27b`).
2. One after-click screenshot cut off what changed (#7 laptop: lamp head off-screen) → before/after screenshots,
   framed on the clicked block.
3. On phones that framing left Add to cart under Bubl's sticky bottom bar → cart stayed empty, #10 reached an empty
   checkout (fixed: click from the middle of the screen; framing keeps clear of bottom bars).
4. "Too many requests" used up the AI's two tries and showed as "not sure" (fixed: waiting doesn't use a try; if
   still busy, it says so).
5. A click before the page's scripts were ready did nothing once (#7 phone) (fixed: wait for the page to load).
6. #10 used a 3-step browser flow that could never finish → owner's rule: browser only for 1 page + 1 click.

## 5. Can it test a real AI app?

**Setup.** A demo "AI feature", `POST /api/demo-ai/answer` `{"text": "…"}` → `{"answer": "…"}`: a Bubl shop
assistant on Groq (`openai/gpt-oss-20b`), clearly separated in `api/_lib/demo_ai.py`. **Planted flaw** (prompt
version 1): a leftover line "Never mention prices or discounts; tell the shopper to check the website". In Eval
Co-pilot, project **"Demo AI (audit)"** (link `https://eval-copilot.vercel.app`) with 5 golden pairs, each
`POST /api/demo-ai/answer` with the question as `request_body`:

| # | User asks | Good result | Checks |
|---|---|---|---|
| 1 | How much is the Solaris lamp? | gives ₹1,680 | code `text_has 1,680` + `ai_judge` |
| 2 | Is the Walkie cheaper than Solaris? | yes, with both prices | code `text_has 564` + `ai_judge` |
| 3 | What colours does Solaris come in? | Black, Sand, Rust Red | code `text_has` ×2 + `ai_judge` |
| 4 | How long does Solaris run on one charge? | 7 h max, up to 70 h low | code `text_has 70` + `ai_judge` |
| 5 | Can I charge Solaris with a USB cable? | yes, USB-C, ~4 h, under 50 words | code `text_has USB` + `ai_judge` |

**What happened**
- **Run 1:** the tool sent the POST, read the JSON answer and **caught the flaw**: #1 and #2 failed on phone and
  laptop (6 pass, 4 fail). Why lines: "Page only says to check website for price, no ₹1,680 mentioned"; "Answer
  says Walkie is cheaper but does not provide the prices". 3 things to fix: "Include the exact price (₹1,680)…".
- **Run 2 (no changes):** 7 pass, 3 fail. One verdict flipped: #2 laptop passed, because the demo AI itself happened
  to give the prices that time despite its bad rule (its answer had "₹564"). **The judge was stable:** in all 20
  rows the code check and the AI judge agreed. The flip came from the AI app, not from a weak check, which is
  exactly what a builder needs to see.
- **Fix:** prompt version 2 (prices allowed, exact), redeployed. **Re-run changed** (#1, #2 ticked) → Run 3:
  4/4 pass ("₹1,680 (taxes included, free shipping)"; "Walkie is ₹564, while Solaris is ₹1,680"), **"Good now?
  yes"** for both, **Compare with Run 1: 4 FIXED**, with Run 2: 3 FIXED + 1 same; **Run 1 untouched** (still 6/4).

**Honest answers**
- **Can a builder point it at their AI feature today?** Yes, if the feature is a public HTTP endpoint on their
  site's host. They type: the site link (project), and per pair the path (`/api/…`), method `POST`, the JSON body
  (e.g. `{"text": "…"}`), and checks. They don't need to say where the answer is in the JSON: text checks and the AI
  judge read the whole reply; `count_equals` can read a dotted path.
- **What breaks:**
  - **Endpoints that need an API key or login:** no way to send headers, on purpose (the app must never store a
    site's keys). Use a public demo or staging endpoint.
  - **Streaming answers** (server-sent events): read as raw text until the 15 s timeout, which is messy.
  - **Slow answers over 15 s:** the pair fails with "timed out".
  - **Chat apps that need a session or several turns:** each pair is one request.
  - **Endpoints on another host:** `request_url` must be a path on the project's own site.
  - **Very long JSON:** only the first ~6,000 characters go to the AI judge.
- **Is the AI judge trustworthy here?** On these 30 judged rows (3 runs × 5 pairs × 2 devices) I read every answer
  and every verdict: **0 disagreements** with a careful person. It quoted the actual evidence ("no ₹1,680
  mentioned"). Caveat: "under 50 words" can only be judged by the AI, so a strict word count isn't guaranteed.
  The owner's 3 hand grades are still **Human to do**.
- **Smallest change that would help most:** a code rule `max_words` (count words in the answer) so length limits are
  checked by code, not AI. It needs a database rule change + UI label, so it's listed, not built today. Header
  support is deliberately not offered (no stored keys).

## 6. Hackathon checklist

| Item | Status | Evidence / what's missing |
|---|---|---|
| Live link anyone can open | done | https://eval-copilot.vercel.app (Vercel login wall off) |
| Public repo | done | GitHub says PUBLIC |
| Login works, RLS proven by a two-user test | done | 93/93 probes today + earlier tests |
| Every feature traces to a need | done | needs 1–15 + additions 1–5 all mapped to a screen / door (README needs list ↔ screens) |
| AI judge checked against 3 hand-graded pairs | **Human to do** | you grade 3 pairs by hand and compare with the judge; my read of 30 demo rows found 0 disagreements |
| No-go respected: no unchecked AI judge | done | every AI verdict shows its why; unsure / busy → "a person needs to check this" |
| Runs never overwritten (history is a row) | done | results insert-only; A couldn't update / delete its own results; Run 1 untouched after re-runs |
| Only public links stored, no user-site keys or customer data | done | private / local links refused; no header or key fields; screenshots never stored |
| Paper sketches photographed (Moves 2, 3, 4) | **Human to do** | |
| Classmate test (Brajesh): fail → fix → re-run → pass | **Human to do** | the tool flow is proven on the demo AI; Brajesh has to change his real site |
| Stranger test | **Human to do** | |
| Submission template filled | **Human to do** | |

**Before the 9 AM check-in (classmate test)**
1. Decide on Groq: upgrade to Dev Tier (console.groq.com) **or** plan at most ~4 full Bubl runs that day.
2. Sit with Brajesh: open Bubl Solar → Golden tests → **Run all approved pairs**. Answer the "You check" rows.
3. Pick one real failing case with him (today: #6, colour price) or one he cares about, let him change his site,
   tick it → **Re-run changed** → show "Good now?" and Compare. Screenshot Run 1 vs Run 2.
4. Photograph your paper sketches (Moves 2, 3, 4).

**Before the 9 PM final submission**
1. Stranger test: a person who has never seen the app signs up, adds a site and runs it; note where they got stuck.
2. Hand-grade 3 pairs and compare with the judge (write it in a short note).
3. Turn on Supabase → Authentication → "Leaked password protection".
4. Fill in the submission template (live link, repo, AUDIT.md, screenshots).
5. Optional: delete the audit test accounts and the demo endpoint; make new Groq and Browserless keys (both were
   pasted in chat).

## 7. Fixes made during the audit (commits on `main`)

| Commit | Fix |
|---|---|
| `9c068d3` | Vision model: Groq retired Llama 4 Scout → `qwen/qwen3.8-27b`; vision failures logged |
| `0eecb7f` | Before / after screenshots around the click, framed on the clicked block; Groq compares both |
| `61e12c0` | Click from the middle of the screen (phone sticky bar); framing above bottom bars; "too many requests" no longer ends as "not sure" |
| `ed50cc6` | Owner's rule: browser only for one page + one click (longer flows → code + AI); wait for page load before clicking; demo AI endpoint; `projects` policy advisor fix (+ `db/migration_06…`) |
| `382eeff` | Demo AI: fixed prompt (version 2), for the AI-app test |
| this commit | AUDIT.md, 02.2.md, summary.md; REPORT.md outdated model name and timing fixed |

Also done outside git: `BROWSERLESS_TOKEN` added to Vercel Production (sensitive) and redeployed; Bubl data: old #10
switched off, new #12 (order summary, code + AI) added; migration `projects_policy_initplan` applied live.

## 8. Open issues, ranked by risk

1. **Groq free-plan daily cap for screenshots** (200k tokens/day ≈ 5–6 full runs with screenshots). Fix: Dev Tier;
   or send smaller screenshots (laptop at 0.75 scale) and the before picture only when needed.
2. **Human "Looks wrong" doesn't change the outcome.** Option: keep results insert-only but compute the shown outcome
   (and counts, 3 worst, compare, good now) from result + human answers at read time. Medium change.
3. **No usage limits**: open sign-up, no per-account cap on runs / AI / browser; public demo endpoint. Add a daily
   run cap per account, and remove the demo after the hackathon.
4. **Browser pairs are slow** (45–80 s each; a full Bubl run takes ~6–7 min). Fine for now; tell testers to wait.
5. **Browser clicks can still be flaky on some pages** (one #7 phone miss in Run 10, fixed by waiting for load; watch
   it).
6. **The 10-pair limit is only in the screen**, not on the server (Bubl now has 12 pairs, 11 approved).
7. **Temporary workflow** `.github/workflows/live-check.yml` (write permission, pushes screenshot branches) and
   scratch branches `m7-shots`, `landing-shots`: delete when done.
8. **Leaked password protection off** in Supabase (dashboard switch).
9. **Icon library loaded from a CDN without an integrity hash** (pinned version). Low.
10. **Link safety:** private addresses are refused by name / IP and re-checked on every redirect, but a DNS trick
    between check and request is still possible; browser clicks may leave the site (only payment / login / captcha are
    stopped). Low (Browserless runs off our network).
11. **No server-side length rule** (`max_words`) for AI answers (section 5).

## 9. For my check-in: 5 real, verifiable bullets

1. **Live and private:** https://eval-copilot.vercel.app, two-user security test 93/93 passed (AUDIT.md §3).
   Attach: AUDIT.md section 3.
2. **Real browser works:** it clicks Add to cart, Turn On and colour swatches on a real Shopify store as a phone and a
   laptop, and the AI compares before / after screenshots ("lamp glowing, button now says Turn Off").
   Attach: the Run 12 results page.
3. **Caught a planted bug in an AI feature:** the demo shop assistant hid prices; Run 1 failed #1/#2 with "no ₹1,680
   mentioned"; after the prompt fix, Re-run changed showed 4 FIXED and "Good now? yes". Attach: the Demo AI Run 3
   "Good now?" panel.
4. **History is never overwritten:** Run 1 stays next to Run 2 with FIXED / BROKE / same. Attach: a Compare screenshot.
5. **Honest about limits:** blocked sites say "can't test", payment / login pages go to a person, a busy AI says
   "busy". Attach: a row with "Payment page, a person needs to check this".

## 10. Human to-do list (with times)

| When | What | Time |
|---|---|---|
| Before 9 AM | Decide Groq Dev Tier (or plan ≤ 4 runs) | 10 min |
| Before 9 AM | Classmate test with Brajesh (run → he fixes one thing → re-run → pass) | 45 min |
| Before 9 AM | Photograph paper sketches (Moves 2, 3, 4) | 10 min |
| Before 9 AM | Answer the waiting "You check" rows in the newest Bubl run | 10 min |
| Before 9 PM | Stranger test | 30 min |
| Before 9 PM | Hand-grade 3 pairs vs the AI judge | 20 min |
| Before 9 PM | Supabase: turn on leaked password protection | 2 min |
| Before 9 PM | Submission template | 30 min |
| Optional | Delete audit test accounts, demo endpoint, temp workflow / branches; new Groq + Browserless keys | 20 min |
