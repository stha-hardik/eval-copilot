# Eval Co-pilot

## 1. What it does

A builder thinks their website works because they only tried the things they picked. Eval Co-pilot takes up to 10 golden pairs (what a user does, and what a good result looks like), runs every one against your live site as a phone and as a laptop, and marks each as pass, fail or can't test, with a one-line reason. It picks the 3 worst fails, and it keeps Run 1 next to Run 2 so you can prove a fix worked. The first user is Brajesh, who runs a Shopify store at https://bublsolar.com.

## 2. Live link

Live app: https://eval-copilot.vercel.app

Repo: https://github.com/stha-hardik/eval-copilot

## 3. How to use it

1. **Sign up** with your email and a password of at least 8 characters, then log in.
2. **Add your site.** On "My sites", click **New site**, give it a name, and paste the public link of your live site. Only that link is stored.
3. **Write pairs.** On the site page, type what a user does and what a good result looks like (or press the mic and speak). Click **Tidy with AI** to turn it into a clean pair with checks. Or click **Suggest pairs** for up to 5 ideas, marked "suggested".
4. **Edit, approve, prioritise.** Change any pair you like, tick **Approved**, and press **Priority** on the pairs that matter most. Only approved pairs run.
5. **Run all.** The results fill in live, one row per pair per device, with pass, fail or can't test.
6. **Read the results.** The 3 key points sit at the top. When a check needs your eyes (layout, colour, checkout), press **Looks right** or **Looks wrong**.
7. **Fix your site, then prove it.** Tick the pairs you changed, add anything else under **Other changes**, and press **Re-run changed**. You get "Good now? Yes or No" for each. Press **Compare with an earlier run** to see FIXED, BROKE or same.

## 4. How it's built

| Part | What it is |
|---|---|
| Screens | Plain HTML, CSS and JavaScript in `/public`. No build step. |
| Server | Python (FastAPI) in `api/index.py`, running on Vercel. One address per action. See `docs/API.md`. |
| Login and database | Supabase: email and password login, and a Postgres database with Row Level Security (the database's own rules that stop one builder seeing another's data). The server talks to Supabase as the logged-in user, never with a service-role key. |
| AI | Groq, model `openai/gpt-oss-120b`, for five jobs: tidy a pair, suggest pairs, judge a fuzzy check, explain the 3 worst fails, and turn "other changes" into a check. |
| Reading the site | Python `requests` only, as a phone and as a laptop. Shopify carts are tested by adding to the cart and reading it back. |
| Voice | The browser's built-in speech-to-text. It works in browsers that support it. |

**Code vs AI vs you.** Code decides the status of every check, the pass and fail counts, the 3 worst fails, and the Run 1 vs Run 2 comparison. The AI judges the fuzzy checks (such as "does the page show the battery runtime?"), writes the one-line reason for each fail, and writes the diagnosis. You decide the visual checks, such as layout, overlaps and colours. The AI never invents numbers or status codes.

## 5. Project layout

```
eval-copilot/
├── api/
│   ├── index.py          every /api door (FastAPI)
│   └── _lib/
│       ├── groq.py       the five AI jobs
│       ├── site.py       reads the live site (phone, laptop, Shopify cart)
│       └── supa.py       talks to Supabase as the logged-in user
├── public/
│   ├── index.html        log in / sign up
│   ├── home.html         my sites
│   ├── project.html      golden pairs
│   ├── run.html          results
│   ├── css/              app.css, project.css, run.css
│   └── js/               api.js, login.js, home.js, project.js, run.js
├── db/                   supabase_setup.sql and two migrations
├── docs/                 API.md, UI_KIT.md, UIUX_RULES.md
├── scripts/              seed_bubl.py, smoke_live.py
├── tests/                automated tests (pytest)
├── BUILD_PROMPT.md, PLAN.md, TESTING.md, DECISIONS.md
└── vercel.json, requirements.txt, .env.example
```

## 6. Run it locally

You need Python 3.10 or newer (Vercel runs 3.12). If `python3` is older, run `uv venv --python 3.12` and `source .venv/bin/activate` first. Install the packages from the repo root:

```
pip install -r requirements.txt uvicorn
```

Set the three variables from `.env.example` in your shell only (never in a file you commit):

```
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_ANON_KEY="your-anon-key"
export GROQ_API_KEY="your-groq-key"
```

**Recommended: `vercel dev`.** Install the Vercel CLI (`npm i -g vercel`) and run `vercel dev` from the repo root. It serves the pages in `/public` and the API in `/api` together, at http://localhost:3000. The first time, it may ask you to link the folder to your Vercel project.

**API only:** `uvicorn api.index:app --reload --port 8000`, run from the repo root. Then open http://localhost:8000/api/health and check for `{"ok": true}`. This does not serve the pages, so use `vercel dev` to click through the screens.

**Tests:** `pip install pytest`, then `python3 -m pytest -q tests/`.

## 7. Database

1. In your Supabase project, open the SQL Editor and run `db/supabase_setup.sql`. It creates the tables and the rules. Do not run the commented-out OPTIONAL SEED block; add pairs through the app.
2. Then run `db/migration_02_lock_rls_auto_enable.sql`, and after it `db/migration_03_fk_indexes.sql`.
3. Go to **Authentication → Sign In / Providers → Email** and turn **off "Confirm email"**. Otherwise new accounts must click a link in an email before they can log in.

## 8. Safety

- No secret is in the browser or in git. The Groq and Supabase keys live only in Vercel's environment variables (or in your shell when testing locally).
- The database refuses to change or delete old runs and results. A re-run adds new rows, so Run 1 is never overwritten.
- Only the public link of a site is stored. No site passwords, keys or customer data.
- Each builder sees only their own sites.

## 9. More

- [TESTING.md](TESTING.md): what was tested, the steps and the results, including the two-user security test
- [DECISIONS.md](DECISIONS.md): the choices made along the way
- [REPORT.md](REPORT.md): the final report, with the live link and Run 1 results for Bubl Solar
- [docs/API.md](docs/API.md): every door the browser calls
