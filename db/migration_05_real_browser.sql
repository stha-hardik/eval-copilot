-- Applied as migration "m7_real_browser" (M7: the real browser replaces human checks).
-- New check rules decided with a real browser: browser_count (code reads a count after real clicks)
-- and ai_vision (the AI judges one screenshot). "manual" stays only as the last-resort fallback.
alter table public.checks drop constraint checks_rule_check;
alter table public.checks add constraint checks_rule_check check (rule in
  ('status_ok','text_has','text_absent','count_equals','min_results','ai_judge','browser_count','ai_vision','manual'));
-- What the browser does before checking, e.g. [{"goto":"/products/solaris"},{"click":"text=Sand"}]
alter table public.checks add column steps jsonb;
-- How a result was decided: a plain page read, the real browser, or handed to a person.
alter table public.results add column via text not null default 'fetch' check (via in ('fetch','browser','human'));
