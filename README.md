# Eval Co-pilot

## 1. What it does

A builder thinks their website works because they only tried the things they picked. Eval Co-pilot takes up to 10 golden pairs (what a user does, and what a good result looks like), runs every one against your live site as a phone and as a laptop, and marks each as pass, fail or can't test, with a one-line reason. It picks the 3 worst fails, and it keeps Run 1 next to Run 2 so you can prove a fix worked. The first user is Brajesh, who runs a Shopify store at https://bublsolar.com.

### What it must do (needs)

1. Log in; each builder sees only their own sites.
2. Take the public link of a live site and up to 10 golden pairs (what a shopper does + what a good result looks like).
3. Test every pair on a phone and on a laptop, and mark each pass / fail / can't test with a one-line reason.
4. Pick the 3 worst fails and say what to change.
5. Never change an old run: Run 1 sits next to Run 2 so a fix can be proven.
6. Check what a shopper would click or look at (add to cart once, change colour, menu on a phone, preview) without a person doing it.
7. Use the real browser only when a plain page read can't answer.
8. Hand a check to a person only when the browser can't or mustn't go further, and say why.
9. Never pay, log in, create accounts or place orders on the user's site.
10. Show which tests used the real browser.

## 2. Live link

Live app: https://eval-copilot.vercel.app

- **`/`** is the public landing page: what the app does, three example tests from a made-up shop (labelled as
  examples), a "3 things to fix first" preview, how it works in 4 steps, and **Test yours**. Logged out, the top
  right shows **Log in** and **Sign up** and "Test yours" opens sign up; logged in, it shows **Dashboard** and
  "Test yours" opens your projects. The page is static: it only looks in the browser to see if you're logged in.
- **`/login`** and **`/signup`** are the log in and sign up screen. After either you go straight to your projects (the dashboard). The login is remembered in that browser, so coming back to the landing page later shows **Dashboard** instead of Log in / Sign up.
  Opening a page that needs a login (for example your projects) while logged out sends you to `/login`, and
  after logging in you go straight back to that page.
- **Light and dark theme.** It follows your device at first. Switch it any time from the avatar menu at the top
  right (**Dark theme**, between "Signed in as" and "Log out"); your choice is remembered on that browser.

Repo: https://github.com/stha-hardik/eval-copilot

## 3. How to use it

1. **Sign up.** Open the live link and press **Test yours** or **Sign up**, then use your email and a password of at least 8 characters. Press **Dashboard** to reach your projects.
2. **Add your site.** On "My sites", click **New site**, give it a name, and paste the public link of your live site. Only that link is stored.
3. **Write pairs.** On the site page, type what a user does and what a good result looks like (or press the mic and speak). Click **Tidy with AI** to turn it into a clean pair with checks. Or click **Suggest pairs** for up to 5 ideas, marked "suggested".
4. **Edit, approve, prioritise.** Change any pair you like, tick **Approved**, and press **Priority** on the pairs that matter most. Only approved pairs run.
5. **Run all.** The results fill in live, one row per pair per device, with pass, fail or can't test.
6. **Read the results.** The 3 key points sit at the top. Each row shows how it was checked: by reading the page, or with a **Real browser** that clicked and looked like a shopper. Only when the app can't finish a check itself (for example it reached a payment page, which it never touches) does it show **You check** with the reason; then press **Looks right** or **Looks wrong**.
7. **Fix your site, then prove it.** Tick the pairs you changed, add anything else under **Other changes**, and press **Re-run changed**. You get "Good now? Yes or No" for each. Press **Compare with an earlier run** to see FIXED, BROKE or same.

## 4. How it's built

| Part | What it is |
|---|---|
| Screens | Plain HTML, CSS and JavaScript in `/public`. No build step. |
| Server | Python (FastAPI) in `api/index.py`, running on Vercel. One address per action. See `docs/API.md`. |
| Login and database | Supabase: email and password login, and a Postgres database with Row Level Security (the database's own rules that stop one builder seeing another's data). The server talks to Supabase as the logged-in user, never with a service-role key. |
| AI | Groq, model `openai/gpt-oss-120b`, for five jobs: tidy a pair, suggest pairs, judge a fuzzy check, explain the 3 worst fails, and turn "other changes" into a check. |
| Reading the site | Python `requests` first, as a phone and as a laptop. Shopify carts are tested by adding to the cart and reading it back. |
| Real browser | [Browserless](https://www.browserless.io) runs a real Chrome for us (nothing is installed on Vercel). Used only for checks that need a click or a look: it does the steps (open, click, wait), reads the cart, and takes one screenshot that the AI looks at (Groq vision model `meta-llama/llama-4-scout-17b-16e-instruct`). |
| Voice | The browser's built-in speech-to-text. It works in browsers that support it. |

**Who decides each check: the simplest way first.** For every check, on every device, code picks in this fixed order:

1. **Reading the page** (fast, free): page opens, words shown or not shown, counts, number of results, and AI questions about the page text.
2. **Real browser**, only when a test needs a click or a look: "count after real clicks" (for example Add to cart once → exactly 1 item) and "AI looks at the screen" (the colour picked, the menu on a phone, the lamp lit up). One browser visit per pair and device, phone then laptop, at most one screenshot, at most 12 visits per run. Also used once when a page shows almost no text to a plain read.
3. **You, only as a last resort, always with the reason**: the browser reached a payment, login or "are you a robot?" page; the AI wasn't sure from the screenshot twice; the real browser was unavailable, busy, out of its monthly allowance or too slow; or the run used its 12 browser visits.

Code also decides the pass and fail counts, the 3 worst fails and the Run 1 vs Run 2 comparison. The AI writes the one-line reason for each fail and the diagnosis, and never invents numbers or status codes. The browser never types, pays, places orders, logs in or creates accounts, and refuses buttons like "Buy it now", "Pay", "Log in" or "Sign up".

## 5. Project layout

```
eval-copilot/
├── api/
│   ├── index.py          every /api door (FastAPI)
│   └── _lib/
│       ├── groq.py       the AI jobs (incl. judging a screenshot)
│       ├── browser.py    the real browser (Browserless), safety rules, reasons
│       ├── browser_fn.mjs  the steps the hosted browser runs (open, click, read cart, screenshot)
│       ├── site.py       reads the live site (phone, laptop, Shopify cart)
│       └── supa.py       talks to Supabase as the logged-in user
├── public/
│   ├── index.html        public landing page
│   ├── favicon.svg       the Eval Co-pilot mark (check in a ring + co-pilot dot), also in every logo tile
│   ├── login.html        log in / sign up (/login, /signup)
│   ├── home.html         my sites
│   ├── project.html      golden pairs
│   ├── run.html          results
│   ├── css/              app.css (light + dark tokens), landing.css, project.css, run.css
│   └── js/               theme.js, api.js, ui.js, landing.js, login.js, home.js, project.js, run.js
├── db/                   supabase_setup.sql and its migrations (02–05)
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

Set the variables from `.env.example` in your shell only (never in a file you commit). `BROWSERLESS_TOKEN` is optional; without it, real-browser checks are handed to you with the reason "The real browser isn't set up":

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
2. Then run `db/migration_02_lock_rls_auto_enable.sql`, `db/migration_03_fk_indexes.sql`, `db/migration_04_ordered_created_at.sql` and `db/migration_05_real_browser.sql`, in that order.
3. Go to **Authentication → Sign In / Providers → Email** and turn **off "Confirm email"**. Otherwise new accounts must click a link in an email before they can log in.

## 8. Safety

- No secret is in the browser or in git. The Groq, Supabase and Browserless keys live only in Vercel's environment variables (or in your shell when testing locally). `/api/health` only says whether a browser key exists, never what it is.
- The real browser never types into forms, pays, places orders, logs in or creates accounts. It stops at payment, login and bot-check pages and hands that check to you with the reason. Screenshots are never stored.
- The database refuses to change or delete old runs and results. A re-run adds new rows, so Run 1 is never overwritten.
- Only the public link of a site is stored. No site passwords, keys or customer data.
- Each builder sees only their own sites.

## 9. More

- [TESTING.md](TESTING.md): what was tested, the steps and the results, including the two-user security test
- [DECISIONS.md](DECISIONS.md): the choices made along the way
- [REPORT.md](REPORT.md): the final report, with the live link and Run 1 results for Bubl Solar
- [docs/API.md](docs/API.md): every door the browser calls
