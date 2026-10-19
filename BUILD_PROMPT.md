# Build prompt: Eval Co-pilot (run this end to end)

You are my coding agent. Build, set up, deploy and test this whole app **by yourself, from start to finish**. I am a no-code builder and I want to come back to a working live link.

Work through every milestone at the bottom without stopping. After each milestone: test it yourself, commit, push, and move on. Only stop and ask me for the things listed in **"The only things you ask me for"**. When everything is done, write the final report described at the end.

You have: the GitHub CLI (`gh`), a **Supabase** connector, and a **Vercel** connector (use the Vercel CLI as a fallback). Use them.

---

## 0. The only things you ask me for

Ask these **once, at the very start**, in one message, then don't stop again:

1. **The Supabase project name** I created (you find its id, URL and keys yourself with the Supabase connector).
2. **The GitHub repo** name (you're probably already inside it; confirm with `gh repo view`). It must be **public** for my submission; if it's private, make it public.
3. **My Groq API key.** Never print it, never commit it, never put it in a file in the repo. Put it straight into Vercel's environment variables. For local testing, only set it in your shell for that session.
4. **The email I want my own account on.** You create that account through the app with a strong random password and tell me the password **in chat only** (never in the repo or any file).
5. **One switch for me to flip:** Supabase dashboard → Authentication → Sign In / Providers → Email → turn **off "Confirm email"**, so new accounts can log in straight away. Tell me this in the same first message. Check it worked before M2; if sign-up still asks for confirmation, remind me once.

Everything else you decide yourself, following this file. If something is unclear, pick the simplest option that matches this file, write it down in `DECISIONS.md`, and keep going.

---

## 0.5 How you work: Opus plans, sub-agents do the hands-on work

You (the main agent, **Opus**) are the lead. You plan, decide, review and test. You hand the hands-on work to **sub-agents** using your Agent / Task tool with a model setting:

| Model | Use it for | Examples in this build |
|---|---|---|
| **Opus** (you, main agent) | Planning, decisions, anything security-critical, reviewing every sub-agent's work, final testing | The plan for each milestone · login + RLS + keys · the run logic and "code vs AI decides" · reviewing diffs · the two-user RLS test · `REPORT.md` |
| **Sonnet** sub-agents | Writing code for one well-defined piece | One `/api` door or a small group of doors · one screen (HTML + CSS + JS) · the Groq prompt helpers · the Shopify cart helper |
| **Haiku** sub-agents | Menial, fast, low-risk tasks | Reading the UI/UX skill repo and summarising its rules · fetching bublsolar.com to find real product / collection handles · writing `README.md`, `TESTING.md`, `.env.example` · checking for missing files, typos, broken links · grepping the repo for leaked secrets |

How to run it:
1. **At the start of each milestone**, write a short plan in `PLAN.md`: the pieces, which model does each, and which files each sub-agent owns.
2. **Give every sub-agent a full brief.** They start with no memory of this file, so paste the relevant sections (needs, table columns, door spec, design rules) into each brief, plus the exact files they own and what "done" means.
3. **One owner per file.** Two sub-agents never edit the same file at the same time. Run independent pieces in parallel (for example: the screens with Sonnet while Haiku finds the Bubl handles).
4. **You review everything before it's committed.** Read each diff, run it, and fix or send it back. Sub-agents never commit, push, touch Supabase or Vercel, or handle the Groq key; only you do.
5. **Keep the security-critical work yourself:** auth, the RLS test, environment variables, and anything that writes to Supabase's schema.
6. If a sub-agent fails twice on the same piece, do it yourself and note it in `DECISIONS.md`.

---

## 1. What the app does

A builder thinks their website works because they only tried the things they picked. **Eval Co-pilot** takes up to 10 **golden pairs** (what a user does + what a good result has), runs every one against the builder's **live site** as a phone and as a laptop, marks each pass / fail / can't test with a one-line why, picks the **3 worst fails**, and keeps **Run 1 next to Run 2** so the builder can prove a fix worked.

First real user: Brajesh, who runs a Shopify store at https://bublsolar.com.

**The win:** the builder changes something on their site, presses **Re-run changed**, and a case that failed now passes.

---

## 2. Needs (every feature must trace back to one of these)

1. Log in; each builder sees only their own projects
2. Paste the live link to test (public link only, never a key)
3. Ask for 10 golden pairs from real use: what the user does + what a good result has
4. Show an example pair beside the box (e.g. "Searches 'Solaris' → Solaris appears, link opens the right page")
5. Let the builder type or speak a rough pair; the AI tidies it into a clean golden pair
6. Optional: a "Suggest pairs" button below the ask; the AI reviews the site like a conversion expert, pairs marked "suggested"
7. The builder edits and approves every pair, suggested or not, and marks any as priority, before anything runs
8. Split each good result into small checks marked code / AI / human; the golden pair is the standard
9. Check every pair twice: as a phone and as a laptop
10. Run all pairs against the live site in one click
11. Show pass / fail per check, per device, with what the site returned; for every fail, the AI writes a one-line why
12. Say "can't test" honestly when the site blocks us or a check needs human eyes
13. The AI does the diagnosis: code picks the 3 worst fails, the AI explains each, backed by what the site showed
14. Never overwrite the old run; Run 1 sits next to Run 2 with FIXED / BROKE per case
15. Show the cases marked priority first (Brajesh: #8 add to cart)

**Additions**
1. Home page project manager: only your own sites, each with last run, pass count, date; open + new project. No ranking.
2. Results page updates on screen as each pair finishes: on top a "how to read this" key for each column; then the table, one row per pair per device; below it the 3 key points from need 13
3. "Re-run changed": the builder ticks the pairs they changed, and only those run again
4. "Other changes" box: the builder writes anything else they changed; the AI turns it into a check to approve; it runs too
5. After the re-run, a small result per pair: what changed + yes / no, good now?

---

## 3. Stack (do not change)

| Piece | Choice |
|---|---|
| Code | This GitHub repo (public) |
| Hosting | Vercel, connected to this repo, auto-deploy on push |
| My server | **Python** serverless functions in `/api` on Vercel (FastAPI is fine) |
| Screens | Plain HTML + CSS + vanilla JavaScript in `/public` (no React, no build step) |
| Login + database | Supabase (email + password, Postgres, Row Level Security) |
| AI | Groq, model `openai/gpt-oss-120b`, `https://api.groq.com/openai/v1/chat/completions` |
| Reading the user site | Python `requests` only (no browser, no Playwright) |
| Voice input | The browser's built-in speech-to-text (Web Speech API) |

### Project layout on Vercel (use exactly this, it's the reliable way)

```
/api/index.py        one FastAPI app with every /api/... door
/public/             index.html + other pages, css, js (served at the site root)
/db/supabase_setup.sql
requirements.txt     fastapi, requests, httpx (or supabase), etc.
vercel.json          rewrite /api/(.*) → /api/index ; functions maxDuration 60
```

Test the deploy with `/api/health` before building anything else on top.

### Environment variables (Vercel only, never in code or the browser)

| Name | What it is |
|---|---|
| `SUPABASE_URL` | Supabase project URL (get it with the Supabase connector) |
| `SUPABASE_ANON_KEY` | Supabase anon / publishable key (connector) |
| `GROQ_API_KEY` | From me. Server only. |

Never use the Supabase service-role key. My server talks to Supabase **as the logged-in user** by passing the user's access token, so the security rules always apply. Add `.env.example` (names only) and put `.env` in `.gitignore`.

---

## 4. UI / UX design

My UI/UX design skill is in one of my public GitHub repos. Find it yourself: run `gh repo list stha-hardik --limit 100` and pick the repo for the UI/UX design skill (name like "ui-ux-design…"). Read its `SKILL.md` and any reference files **before** building any screen, and follow it for layout, typography, spacing, colour, states and copy. If two rules conflict, the skill wins on looks and this file wins on features.

Minimum bar no matter what: works on a phone, clear loading / empty / error / success states, one obvious main button per screen, plain words (no jargon on screen).

---

## 5. The database

### 5.1 Set it up (milestone M1)

The full setup script is in `db/supabase_setup.sql` in this repo. Apply it to my Supabase project **with the Supabase connector** (as a migration named `init_eval_copilot`). Then check with the connector that all 8 tables exist with RLS enabled, and run the Supabase security advisor; fix anything it flags. (A note that `owns_project` is a SECURITY DEFINER function is expected and intentional: it lets the rules check project ownership. Leave it.) This script has already been tested on Postgres with two users: setup runs cleanly, user B sees nothing of user A's, old results can't be changed or deleted, and duplicates and a 4th worst fail are refused.

Do **not** run the commented "OPTIONAL SEED" block; you seed through the app instead (milestone M3).

### 5.2 What's in it

| Table | Columns |
|---|---|
| `auth.users` (Supabase login) | id, email, created_at |
| `projects` | id, user_id → users, name, site_url (public link only), created_at |
| `golden_pairs` | id, project_id → projects, position, user_does, good_result, request_url, method (GET / POST), request_body (json), source (builder / suggested), approved, is_priority, created_at |
| `checks` | id, golden_pair_id → golden_pairs, decided_by (code / ai / human), rule (status_ok / text_has / text_absent / count_equals / min_results / ai_judge / manual), expected |
| `runs` | id, project_id → projects, run_number (1, 2, 3…), kind (full / changed), started_at, passed, total |
| `results` | id, run_id → runs, golden_pair_id → golden_pairs, device (phone / laptop), status_code, what_site_said (short text), outcome (pass / fail / cant_test), created_at |
| `result_checks` | id, result_id → results, check_id → checks, passed (true / false / null = human must look), why |
| `changes` | id, run_id → runs, golden_pair_id → golden_pairs (null = "other change"), note, created_at |
| `diagnosis_points` | id, run_id → runs, result_id → results, rank (1–3), explanation |

Rules the database enforces (don't work around them):
- Each builder only sees rows that trace back to their own `projects.user_id`.
- `results` can only be inserted, never updated or deleted. A re-run adds rows. Run 1 is never overwritten.
- One row per run + pair + device. Max 3 diagnosis points per run.

If you truly need a schema change, make it a new migration with the connector, add the same SQL to `db/`, and note why in `DECISIONS.md`.

---

## 6. My server's doors (the browser calls only these)

Every request sends `Authorization: Bearer <supabase access token>`.

| # | CRUD | Method | Address | Package in | Reply |
|---|---|---|---|---|---|
| 1 | Create | POST | `/api/signup` and `/api/login` | `{"email","password"}` | 200 + session · 401 if wrong |
| 1b | Create | POST | `/api/refresh` | `{"refresh_token"}` | 200 + new session (the browser calls this when a door returns 401, then retries once) |
| 2 | Read | GET | `/api/projects` | none | 200 + my projects with last run number, pass count, date |
| 2b | Read | GET | `/api/projects/{id}` | none | 200 + the project, its pairs (with checks) and its runs · 404 if not mine |
| 3 | Create | POST | `/api/projects` | `{"name","site_url"}` | 201 + project id · 400 if link missing |
| 4 | Create | POST | `/api/pairs/tidy` | `{"rough_text","site_url"}` | 200 + clean pair with checks · 5xx if Groq fails |
| 5 | Create | POST | `/api/projects/{id}/suggestions` | none | 200 + up to 5 suggested pairs |
| 6 | Create | POST | `/api/projects/{id}/pairs` | `{"user_does","good_result","request_url","method","request_body","source","checks":[...]}` | 201 + pair id · 400 if a field is missing |
| 7 | Update | PATCH | `/api/pairs/{id}` | `{"approved","is_priority", edits}` | 200 + pair · 404 |
| 8 | Create | POST | `/api/projects/{id}/runs` | `{"kind":"full"}` or `{"kind":"changed","pair_ids":[..],"other_changes":"..."}` | 201 + run id + pair ids to run |
| 9 | Create | POST | `/api/runs/{id}/pairs/{pair_id}` | none | 201 + that pair's results (phone + laptop) |
| 10 | Create | POST | `/api/runs/{id}/finish` | none | 200 + pass count, 3 worst, yes / no per changed pair |
| 11 | Read | GET | `/api/runs/{id}` | none | 200 + table rows + 3 key points · 404 |
| 12 | Read | GET | `/api/runs/{id}/compare?with={old_id}` | none | 200 + FIXED / BROKE / same per pair and device |
| 13 | Update | PATCH | `/api/result-checks/{id}` | `{"passed": true/false}` | 200 (human fills a manual check) |
| 14 | Read | GET | `/api/health` | none | 200 `{"ok": true}` |

**One pair at a time:** the browser creates the run (door 8), calls door 9 once per pair (so the table fills in live and no call hits Vercel's time limit), then door 10. Door 9 is safe to call twice: if that pair already has results in that run, return them instead of inserting again (the database refuses duplicates).

**Run numbers and counts:** `run_number` = the project's highest run number + 1. `total` = number of result rows in the run, `passed` = rows with outcome `pass`; door 10 writes both.

**"Other changes" flow (Addition 4):** on the results page the builder types what else they changed → the browser sends it to door 4 (`/api/pairs/tidy`, Groq job 5) → shows the proposed pair → the builder approves it (door 6, `approved: true`) → its id goes into `pair_ids` for door 8 → door 8 saves a `changes` row with the note and that pair.

### My server calls Groq (same address, five jobs; always ask for JSON)

| # | Job | Send | Expect |
|---|---|---|---|
| 1 | Tidy a pair | rough text + site URL | `{user_does, good_result, request_url, method, request_body, checks:[{decided_by, rule, expected}]}` |
| 2 | Suggest pairs | home page text (stripped) + site URL; act like a conversion (CRO) reviewer | up to 5 pairs, same shape |
| 3 | Judge one check | page text excerpt + golden pair + the check question | `{passed, why}` |
| 4 | Diagnosis | the 3 worst fails code picked + what the site showed | `{points:[{result_id, explanation}]}`, plain words, say what to change |
| 5 | Other changes → check | the builder's note | one new pair + checks to approve |

- Parse JSON; on failure retry once; still failing → `passed = null`, `why = "AI could not judge, please look"`.
- The AI never invents numbers, status codes or counts. Those come from code.
- Strip HTML; send max ~6,000 characters of page text.

---

## 7. How a run works

For each approved pair, request it **twice**:

```
phone  UA: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1
laptop UA: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36
```

- URL = project `site_url` + pair `request_url`. Timeout 15 s.
- Shopify carts: one `requests.Session()` per device; `POST /cart/add.js` then `GET /cart.js`. Read the variant id from `/products/<handle>.json` first when needed.

**Code decides:** 403 / bot block → `cant_test` (not a fail) · other 4xx, 5xx, timeout → `fail` · `status_ok`, `text_has`, `text_absent`, `min_results`, `count_equals` · pass count · Run 1 vs Run 2 · yes / no per changed pair · **picking the 3 worst** (priority first, then failed on both devices, then the rest).

**AI decides:** `ai_judge` checks, the one-line why for every fail, the diagnosis text.

**Human decides:** `manual` checks (layout, overlap, colour swap, checkout). Saved as `passed = null`; the results page shows **Looks right / Looks wrong** buttons (door 13).

Outcome per result: `fail` if any check failed · `cant_test` if blocked or every check is manual · else `pass`. Save `what_site_said` as a short excerpt (≤ 500 characters).

**The 3 worst (door 10):** code picks up to 3 failed results (priority first, then failed on both devices, then by position), Groq job 4 writes the explanation, save them as `diagnosis_points` rank 1–3. Fewer than 3 fails → save only those; zero fails → save none and show "No fails in this run".

**Compare / yes or no:** for each pair and device in the new run, compare with that pair's result on the same device in the **most recent earlier run that tested it**. fail → pass = **FIXED**, pass → fail = **BROKE**, otherwise **same**. For a "changed" run, "good now?" = **yes** when that pair passes on both phone and laptop, else **no**.

---

## 8. Screens

1. **Login / sign up.**
2. **Home: my projects.** Each site with last run, pass count, date. Open · New project. No ranking.
3. **Project: golden pairs.** "What does the user do?" + "What does a good result look like?"; the example pair beside it; mic button; **Tidy with AI**; under it the optional **Suggest pairs** (labelled "suggested"); list of pairs with edit, approve, priority; **Run all**.
4. **Results** (fills in live): "How to read this" key on top (# · what the user does · device · pass / fail / can't test · what the site showed · why) → table (priority first, then fails) → **3 key points** → **Re-run changed** (tick boxes + "Other changes" box) → after a re-run, a panel: what changed + **yes / no: good now?** → **Compare** with any earlier run.

---

## 9. Must not

- No secret in the browser or in git. No service-role key.
- Never update or delete old runs or results.
- Don't store the user site's passwords, keys or customer data. Only the public link.
- No Playwright, headless browser, React or build step.
- No features beyond sections 2 and 8.

---

## 10. Milestones (do all of them; test, commit, push after each)

**M1: Skeleton + database + deploy.**
Repo structure, `vercel.json`, `requirements.txt`, `/api/health`, a hello page. Apply `db/supabase_setup.sql` with the Supabase connector; verify tables + RLS; run the security advisor. Create / link the Vercel project to this repo with the Vercel connector (or CLI), set the 3 env vars, deploy. *Test: the live link opens and `/api/health` returns ok.*

**M2: Login + projects + RLS proven.**
Sign up, log in, log out, create and list projects. *Test yourself:* create two accounts (`tester.a+eval@example.com`, `tester.b+eval@example.com` or similar), create a project as A, and confirm B gets an empty list and a 404 when asking for A's project by id. Write the exact steps and results in `TESTING.md`.

**M3: Golden pairs + Brajesh's data.**
Add / edit / approve / priority, example pair, mic, Tidy with AI, Suggest pairs. Then, logged in as **my** account (the email I gave you; password told to me in chat only), create project **"Bubl Solar"** with site `https://bublsolar.com` and enter these 10 pairs through the app's own doors, approved, with #8 as priority. Use Tidy with AI to propose the checks for each, and fix request URLs by actually fetching the site (e.g. find the real collection and product handles).

| # | User does | Good result |
|---|---|---|
| 1 | Opens bublsolar.com and browses the menu. | Can easily find the product categories, search and cart. Nothing overlaps or blocks the buttons on mobile. |
| 2 | Searches "Solaris". | Solaris appears in the results, and clicking it opens the correct product page. |
| 3 | Searches "lamp for balcony". | Shows at least one suitable lamp, such as Solaris, rather than no results or unrelated products. |
| 4 | Opens "Cabinet Lights" from the menu. | Sees relevant products such as Walkie, Walkie X and Comfort, with working images, prices and product links. |
| 5 | Opens Solaris to understand whether it suits their needs. | Can easily find its dimensions, brightness, charging options, charging time, battery runtime and warranty. Information is consistent across the page. |
| 6 | Changes the Solaris colour from Black to Sand or Rust Red. | The selected colour is clear, the main image matches it, and any price or availability change is shown before adding it. |
| 7 | Uses the "Turn On" preview and browses product photos. | The preview shows the lamp illuminated, photos load correctly, and the customer can close the enlarged view easily. |
| 8 | Starts with an empty cart, selects one Solaris and clicks "Add to cart" once. **(priority)** | Exactly one lamp in the selected colour is added. The cart does not unexpectedly contain five lamps or extra products. |
| 9 | Adds one Solaris and one Walkie, then refreshes the page. | Both products remain in the cart with the correct options and quantities, without duplicates or missing items. |
| 10 | Checks the final order summary before payment. | Products, colours, quantities and discounts match the cart. Shipping charges and the final payable amount are clearly shown, with no unexplained extras. Any free-shipping promise is honoured. |

**M4: Run.**
Doors 8–10 and 13, phone + laptop, code checks, Groq judge + why, 3 worst, live results page. *Test: run all 10 on bublsolar.com; every row has an outcome; manual checks show the buttons; 3 key points appear.*

**M5: Re-run changed + compare.**
Tick boxes, Other changes box, yes / no panel, compare view. *Test: re-run 2 ticked pairs; Run 1 rows are untouched; compare shows both runs.*

**M6: Polish + docs.**
Friendly errors ("the site blocked us, so we can't test this"), loading / empty states, check against the UI/UX skill once more. Write `README.md` (what it does, live link, how it's built, how to run locally).

Commit message per milestone, e.g. `M2: login, projects, RLS test`.

---

## 11. Final report (write to `REPORT.md` and show me)

- Live link and repo link
- What works, per milestone, with how you tested it
- RLS two-user test result
- Run 1 summary for Bubl Solar (pass / fail / can't test counts, the 3 worst fails)
- Anything that didn't work or that I need to do by hand, in plain words
- Decisions you made on your own (from `DECISIONS.md`)
