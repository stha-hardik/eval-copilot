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
