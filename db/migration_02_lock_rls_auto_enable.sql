-- Applied as migration "lock_rls_auto_enable" (see DECISIONS.md).
-- rls_auto_enable() is Supabase's own event-trigger helper that switches RLS on for new tables.
-- Event triggers don't need EXECUTE grants, so nobody signed in or out needs to call it over the API.
revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
