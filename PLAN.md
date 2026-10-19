# Build plan

Opus (lead) plans, reviews every diff, owns security-critical work (auth, RLS test, env vars,
Supabase schema), commits and deploys. Sonnet sub-agents write well-defined code pieces.
Haiku sub-agents do fast, low-risk chores. One owner per file at any time.

## M1: Skeleton + database + deploy

| Piece | Model | Files owned |
|---|---|---|
| Apply `db/supabase_setup.sql` as migration `init_eval_copilot`, verify 8 tables + RLS, security advisor | Opus | Supabase (connector), `db/migration_0*.sql` |
| Skeleton: `vercel.json`, `requirements.txt`, `api/index.py` (`/api/health`), hello page, `.gitignore`, `.env.example` | Opus (too small to delegate) | those files |
| Read the UI/UX skill repo and summarise its rules | Haiku | scratchpad only |
| Find real bublsolar.com handles | Haiku | scratchpad only |
| Vercel project + 3 env vars + deploy, test `/api/health` | Opus | Vercel (connector) |

Done when: live link opens, `/api/health` returns `{"ok": true}`.

## M2–M5 (built together, since every door shares one contract: `docs/API.md`)

| Piece | Model | Files owned |
|---|---|---|
| API contract, UI kit, browser helper (tokens, refresh-on-401) | Opus | `docs/API.md`, `docs/UI_KIT.md`, `public/js/api.js` |
| Supabase client (as the user), all 14 doors, run logic, "code vs AI decides", 3 worst, compare | Opus | `api/_lib/supa.py`, `api/index.py` |
| Two-user RLS test (database level) | Opus | `TESTING.md` |
| Groq helpers (5 jobs, JSON, retry, safe cleaning) + tests | Sonnet | `api/_lib/groq.py`, `tests/test_groq.py` |
| Site reader (phone/laptop, bot block, Shopify cart, code checks) + tests | Sonnet | `api/_lib/site.py`, `tests/test_site.py` |
| Design system + login + home screens | Sonnet | `public/css/app.css`, `public/index.html`, `public/home.html`, `public/js/login.js`, `public/js/home.js` |
| Golden pairs screen | Sonnet | `public/project.html`, `public/js/project.js`, `public/css/project.css` |
| Results screen (live fill, key points, re-run changed, compare) | Sonnet | `public/run.html`, `public/js/run.js`, `public/css/run.css` |
| End-to-end door tests against an in-memory Supabase stand-in | Sonnet | `tests/fake_db.py`, `tests/test_api.py` |
| UI/UX skill digest | Haiku | `docs/UIUX_RULES.md` |

Opus reviews every diff and runs the tests before each commit.

## M6b: Redesign to the owner's "Tactile Calm" mockups + motion (19 Oct 2026)

Brief for every agent: `docs/REDESIGN.md` (mockups, tokens, motion rules from the owner's
kole-uiux-skills `references/animation.md`, and the mockup decoration we leave out).

| Phase | Piece | Model | Files owned |
|---|---|---|---|
| 1 | Design system (tokens, surfaces, motion), topbar / context nav, login, My projects + New project modal | Sonnet | `public/css/app.css`, `public/index.html`, `public/js/login.js`, `public/home.html`, `public/js/home.js`, `docs/UI_KIT.md` |
| 2 (parallel) | Golden tests screen | Sonnet | `public/project.html`, `public/js/project.js`, `public/css/project.css` |
| 2 (parallel) | Results screen: live table, 3 key points, re-run, "Good now?" panel, compare | Sonnet | `public/run.html`, `public/js/run.js`, `public/css/run.css` |
| 3 | Review every diff, tests, deploy, eval run in Chrome at phone + laptop width | Opus | — |

Phase 2 starts only after Phase 1 is reviewed, because both screens build on the new `app.css`.
