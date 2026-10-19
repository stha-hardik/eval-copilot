-- =====================================================================
-- Eval Co-pilot · Supabase setup (tables + security rules)
-- Paste this whole file into Supabase → SQL Editor → New query → Run.
-- Safe to run once on a fresh project.
-- =====================================================================
-- "users" is Supabase's own login table (auth.users). We don't make our own.

-- ---------- 1. PROJECTS: one website a builder is testing ----------
create table public.projects (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name        text not null,
  site_url    text not null,                 -- public link only, never a key
  created_at  timestamptz not null default now()
);

-- ---------- 2. GOLDEN_PAIRS: what the user does + what good looks like ----------
create table public.golden_pairs (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references public.projects(id) on delete cascade,
  position     int  not null,
  user_does    text not null,
  good_result  text not null,
  request_url  text,                          -- e.g. /search?q=Solaris
  method       text not null default 'GET' check (method in ('GET','POST')),
  request_body jsonb,                         -- e.g. cart add {"id":..,"quantity":1}
  source       text not null default 'builder' check (source in ('builder','suggested')),
  approved     boolean not null default false,
  is_priority  boolean not null default false,
  created_at   timestamptz not null default now()
);

-- ---------- 3. CHECKS: small tests inside one pair ----------
create table public.checks (
  id              uuid primary key default gen_random_uuid(),
  golden_pair_id  uuid not null references public.golden_pairs(id) on delete cascade,
  decided_by      text not null check (decided_by in ('code','ai','human')),
  rule            text not null check (rule in ('status_ok','text_has','text_absent','count_equals','min_results','ai_judge','manual')),
  expected        text,                       -- "Solaris" / "1" / question for the AI
  created_at      timestamptz not null default now()
);

-- ---------- 4. RUNS: one press of Run (history is a row) ----------
create table public.runs (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references public.projects(id) on delete cascade,
  run_number  int  not null,
  kind        text not null default 'full' check (kind in ('full','changed')),
  started_at  timestamptz not null default now(),
  passed      int  not null default 0,
  total       int  not null default 0,
  unique (project_id, run_number)
);

-- ---------- 5. RESULTS: one pair, one device, one run (the proof link) ----------
create table public.results (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references public.runs(id) on delete cascade,
  golden_pair_id  uuid not null references public.golden_pairs(id) on delete cascade,
  device          text not null check (device in ('phone','laptop')),
  status_code     int,
  what_site_said  text,                       -- short text excerpt, not the whole page
  outcome         text not null check (outcome in ('pass','fail','cant_test')),
  created_at      timestamptz not null default now(),
  unique (run_id, golden_pair_id, device)     -- same pair + device can't appear twice in one run
);

-- ---------- 6. RESULT_CHECKS: pass/fail of each check inside one result ----------
create table public.result_checks (
  id         uuid primary key default gen_random_uuid(),
  result_id  uuid not null references public.results(id) on delete cascade,
  check_id   uuid not null references public.checks(id) on delete cascade,
  passed     boolean,                         -- null = human still has to look
  why        text,
  unique (result_id, check_id)
);

-- ---------- 7. CHANGES: what the builder ticked or wrote before a re-run ----------
create table public.changes (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references public.runs(id) on delete cascade,
  golden_pair_id  uuid references public.golden_pairs(id) on delete cascade,  -- blank = "other change"
  note            text,
  created_at      timestamptz not null default now()
);

-- ---------- 8. DIAGNOSIS_POINTS: the 3 worst fails of a run ----------
create table public.diagnosis_points (
  id           uuid primary key default gen_random_uuid(),
  run_id       uuid not null references public.runs(id) on delete cascade,
  result_id    uuid not null references public.results(id) on delete cascade,
  rank         int  not null check (rank between 1 and 3),
  explanation  text not null,
  unique (run_id, rank)                       -- no 4th worst fail, no duplicate rank
);

-- ---------- Speed: indexes on every pointer ----------
create index on public.projects(user_id);
create index on public.golden_pairs(project_id);
create index on public.checks(golden_pair_id);
create index on public.runs(project_id);
create index on public.results(run_id);
create index on public.results(golden_pair_id);
create index on public.result_checks(result_id);
create index on public.changes(run_id);
create index on public.diagnosis_points(run_id);

-- =====================================================================
-- SECURITY RULES (RLS): every builder sees only their own data.
-- Every table traces back to projects.user_id.
-- =====================================================================
alter table public.projects         enable row level security;
alter table public.golden_pairs     enable row level security;
alter table public.checks           enable row level security;
alter table public.runs             enable row level security;
alter table public.results          enable row level security;
alter table public.result_checks    enable row level security;
alter table public.changes          enable row level security;
alter table public.diagnosis_points enable row level security;

-- helper: does the logged-in builder own this project?
create or replace function public.owns_project(p uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.projects where id = p and user_id = auth.uid());
$$;

-- PROJECTS: full control over your own
create policy "own projects" on public.projects
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

-- GOLDEN_PAIRS: full control (edit, approve, mark priority)
create policy "own pairs" on public.golden_pairs
  for all using (public.owns_project(project_id)) with check (public.owns_project(project_id));

-- CHECKS: full control
create policy "own checks" on public.checks
  for all using (exists (select 1 from public.golden_pairs g where g.id = golden_pair_id and public.owns_project(g.project_id)))
  with check (exists (select 1 from public.golden_pairs g where g.id = golden_pair_id and public.owns_project(g.project_id)));

-- RUNS: read, create, and update the pass count. No delete (history is a row).
create policy "read own runs"   on public.runs for select using (public.owns_project(project_id));
create policy "insert own runs" on public.runs for insert with check (public.owns_project(project_id));
create policy "update own runs" on public.runs for update using (public.owns_project(project_id)) with check (public.owns_project(project_id));

-- RESULTS: read + create only. Never update or delete, so Run 1 can't be overwritten.
-- A result's pair must belong to the same project as its run.
create policy "read own results" on public.results for select
  using (exists (select 1 from public.runs r where r.id = run_id and public.owns_project(r.project_id)));
create policy "insert own results" on public.results for insert
  with check (exists (
    select 1 from public.runs r join public.golden_pairs g on g.project_id = r.project_id
    where r.id = run_id and g.id = golden_pair_id and public.owns_project(r.project_id)));

-- RESULT_CHECKS: read + create; update allowed only so a human can fill a blank "manual" check
create policy "read own result_checks" on public.result_checks for select
  using (exists (select 1 from public.results x join public.runs r on r.id = x.run_id where x.id = result_id and public.owns_project(r.project_id)));
create policy "insert own result_checks" on public.result_checks for insert
  with check (exists (select 1 from public.results x join public.runs r on r.id = x.run_id where x.id = result_id and public.owns_project(r.project_id)));
create policy "human fills manual check" on public.result_checks for update
  using (passed is null and exists (select 1 from public.results x join public.runs r on r.id = x.run_id where x.id = result_id and public.owns_project(r.project_id)))
  with check (exists (select 1 from public.results x join public.runs r on r.id = x.run_id where x.id = result_id and public.owns_project(r.project_id)));

-- CHANGES: read + create
create policy "read own changes" on public.changes for select
  using (exists (select 1 from public.runs r where r.id = run_id and public.owns_project(r.project_id)));
create policy "insert own changes" on public.changes for insert
  with check (exists (select 1 from public.runs r where r.id = run_id and public.owns_project(r.project_id)));

-- DIAGNOSIS_POINTS: read + create
create policy "read own diagnosis" on public.diagnosis_points for select
  using (exists (select 1 from public.runs r where r.id = run_id and public.owns_project(r.project_id)));
create policy "insert own diagnosis" on public.diagnosis_points for insert
  with check (exists (
    select 1 from public.runs r join public.results x on x.run_id = r.id
    where r.id = run_id and x.id = result_id and public.owns_project(r.project_id)));

-- =====================================================================
-- ACCESS: logged-in users may use the tables (RLS above still limits rows).
-- Logged-out visitors get nothing.
-- =====================================================================
revoke all on all tables in schema public from anon;
grant select, insert, update, delete on all tables in schema public to authenticated;
revoke execute on function public.owns_project(uuid) from public, anon;
grant execute on function public.owns_project(uuid) to authenticated;

-- =====================================================================
-- OPTIONAL SEED: Brajesh's Bubl Solar project + his 10 golden pairs.
-- 1) Sign up in your app first (or Supabase → Authentication → Add user).
-- 2) Replace YOUR_LOGIN_EMAIL below, then run ONLY this block.
-- request_url values are best guesses for a Shopify store; check them in the app.
-- =====================================================================
/*
with me as (select id from auth.users where email = 'YOUR_LOGIN_EMAIL'),
p as (
  insert into public.projects (user_id, name, site_url)
  select id, 'Bubl Solar', 'https://bublsolar.com' from me
  returning id
)
insert into public.golden_pairs (project_id, position, user_does, good_result, request_url, method, request_body, approved, is_priority)
select p.id, v.pos, v.does, v.good, v.url, v.m, v.body::jsonb, true, v.prio from p, (values
 (1,'Opens bublsolar.com and browses the menu.','Can easily find the product categories, search and cart. Nothing overlaps or blocks the buttons on mobile.','/','GET',null,false),
 (2,'Searches "Solaris".','Solaris appears in the results, and clicking it opens the correct product page.','/search?q=Solaris','GET',null,false),
 (3,'Searches "lamp for balcony".','Shows at least one suitable lamp, such as Solaris, rather than no results or unrelated products.','/search?q=lamp+for+balcony','GET',null,false),
 (4,'Opens "Cabinet Lights" from the menu.','Sees relevant products such as Walkie, Walkie X and Comfort, with working images, prices and product links.','/collections/cabinet-lights','GET',null,false),
 (5,'Opens Solaris to understand whether it suits their needs.','Can easily find its dimensions, brightness, charging options, charging time, battery runtime and warranty. Information is consistent across the page.','/products/solaris','GET',null,false),
 (6,'Changes the Solaris colour from Black to Sand or Rust Red.','The selected colour is clear, the main image matches it, and any price or availability change is shown before adding it.','/products/solaris.json','GET',null,false),
 (7,'Uses the "Turn On" preview and browses product photos.','The preview shows the lamp illuminated, photos load correctly, and the customer can close the enlarged view easily.','/products/solaris','GET',null,false),
 (8,'Starts with an empty cart, selects one Solaris and clicks "Add to cart" once.','Exactly one lamp in the selected colour is added. The cart does not unexpectedly contain five lamps or extra products.','/cart/add.js','POST','{"quantity":1}',true),
 (9,'Adds one Solaris and one Walkie, then refreshes the page.','Both products remain in the cart with the correct options and quantities, without duplicates or missing items.','/cart.js','GET',null,false),
 (10,'Checks the final order summary before payment.','Products, colours, quantities and discounts match the cart. Shipping charges and the final payable amount are clearly shown, with no unexplained extras. Any free-shipping promise is honoured.','/cart.js','GET',null,false)
) as v(pos,does,good,url,m,body,prio);
*/
