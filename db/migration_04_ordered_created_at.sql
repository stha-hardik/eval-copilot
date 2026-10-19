-- Applied as migration "ordered_created_at" (see DECISIONS.md #22).
-- Every row of one INSERT gets the same now(); clock_timestamp() keeps checks and changes in the order written.
alter table public.checks  alter column created_at set default clock_timestamp();
alter table public.changes alter column created_at set default clock_timestamp();
