-- Applied as migration "fk_indexes" (see DECISIONS.md). Speed only: indexes on the 3 pointers
-- the Supabase performance advisor found without one. No change to data or security rules.
create index if not exists changes_golden_pair_id_idx on public.changes(golden_pair_id);
create index if not exists diagnosis_points_result_id_idx on public.diagnosis_points(result_id);
create index if not exists result_checks_check_id_idx on public.result_checks(check_id);
