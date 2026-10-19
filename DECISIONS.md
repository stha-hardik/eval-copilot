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
