-- Audit fix (20 Oct 2026): Supabase performance advisor "auth_rls_initplan".
-- Same rule as before (a builder only sees their own projects); auth.uid() is now read once per query, not per row.
alter policy "own projects" on public.projects
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
