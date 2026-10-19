# API contract (the browser calls only these doors)

Base: same origin, all under `/api`. Every door except signup / login / refresh / health needs
`Authorization: Bearer <supabase access token>`. Errors always look like `{"detail": "plain words"}`.
A 401 means "token expired or missing": the browser calls `/api/refresh` once and retries.

## Shapes

```
Session  = { access_token, refresh_token, expires_at, user: { id, email } }
Check    = { id?, decided_by: "code"|"ai"|"human",
             rule: "status_ok"|"text_has"|"text_absent"|"count_equals"|"min_results"|"ai_judge"
                   |"browser_count"|"ai_vision"|"manual",
             expected: string|null, steps: Step[]|null (browser rules only) }
Step     = {"goto":"/path"} | {"click":"text=<visible words>"|"css=<selector>", "optional"?: true}
         | {"wait": seconds ≤ 5} | {"scroll": "bottom"|pixels}        (at most 8 per check)
Pair     = { id, project_id, position, user_does, good_result, request_url, method: "GET"|"POST",
             request_body: object|null, source: "builder"|"suggested", approved, is_priority,
             created_at, checks: Check[], has_results: bool }
Draft    = { user_does, good_result, request_url, method, request_body, checks: Check[] }   (no id yet)
RunInfo  = { id, project_id, run_number, kind: "full"|"changed", started_at, passed, total }
CheckResult = { id (result_check id), check_id, decided_by, rule, expected, passed: true|false|null, why }
Row      = { result_id, run_id, pair_id, position, user_does, good_result, is_priority, device: "phone"|"laptop",
             status_code: int|null, outcome: "pass"|"fail"|"cant_test", what_site_said, why (one line, "" on pass),
             checks: CheckResult[], via: "fetch"|"browser"|"human",
             human_reason: string ("" unless a browser check was handed to a person) }
Point    = { rank (1-3), result_id, pair_id, position, user_does, device, explanation, what_site_said }
Changed  = { pair_id, position, user_does, note, phone: outcome|null, laptop: outcome|null, good_now: "yes"|"no" }
```

Check rules (`expected` meaning):
- `status_ok`: expected empty → status 200–399 passes. Never decided by AI.
- `text_has` / `text_absent`: expected is a word or phrase; case-insensitive match in the page text
  (HTML stripped) or JSON text.
- `count_equals`: expected `"<path>=<n>"`, e.g. `"item_count=1"` or `"items.length=2"`, read from a JSON reply
  (Shopify `/cart.js`). If the reply is not JSON, counts occurrences of `<path>` text in the page.
- `min_results`: expected `"<n>"`; number of distinct `/products/<handle>` links in the page, or length of the
  product list in a JSON reply.
- `ai_judge`: expected is the yes/no question for the AI, e.g. "Does the page show the battery runtime?".
- `browser_count` (decided by code, **real browser**): expected like `"item_count=1"`; after the steps' real clicks,
  code reads `/cart.js` in that browser and compares (same syntax as `count_equals`).
- `ai_vision` (decided by AI, **real browser**): expected is a yes/no question about what the shopper sees; the AI
  judges ONE screenshot taken after the steps (Groq vision, `{passed, why, confident}`).
- `manual`: legacy / last-resort only (the editor and the AI never create it). Saved as `passed = null`; a human
  answers via door 13.

### Who decides (code, in this fixed order, per check and device)
1. **Fetch** (plain page read) for `status_ok, text_has, text_absent, min_results, count_equals, ai_judge`.
2. **Real browser** for `browser_count, ai_vision`: one Browserless session per pair + device (phone then laptop,
   never at the same time), steps of the pair's first browser check, at most one screenshot reused by every
   `ai_vision` check of that pair. Fallback: a GET page that answers 200 with under ~300 characters of visible
   text (or a JavaScript shell) is re-read once in the browser and the rendered text answers the fetch checks.
3. **A person** only when the browser reaches a payment, login or bot-check page; the AI isn't confident about the
   screenshot twice; the browser service is missing / rejects the key / busy twice / out of units / too slow; or the
   run already used 12 browser sessions. The check is saved with `passed = null` and the reason in `why`; the row
   gets `via: "human"` and `human_reason`; door 13 answers it.
Never: typing into forms, paying, placing orders, logging in or creating accounts on the builder's site. Clicks on
pay / place order / buy it now / log in / sign up / subscribe are refused (door 6/7 answer 400; at run time the
check goes to a person). Screenshots are never stored.

Request fields of a pair:
- `request_url` is a path on the project's site, e.g. `/search?q=Solaris`, `/products/solaris`, `/cart/add.js`.
- `method` GET or POST. `request_body` JSON for POST, e.g. Shopify cart add:
  `{"items":[{"handle":"solaris","option":"Black","quantity":1}]}` (server looks up the variant id from
  `/products/<handle>.json`) or `{"id": 123, "quantity": 1}`. After any POST to `/cart/...` the server also
  reads `/cart.js` in the same session, and the checks run against that cart.

## Doors

| # | Method + path | In | Out |
|---|---|---|---|
| 1 | POST `/api/signup` | `{email,password}` | 200 Session · 400 bad input · 409 needs email confirmation |
| 1 | POST `/api/login` | `{email,password}` | 200 Session · 401 wrong email or password |
| 1b | POST `/api/refresh` | `{refresh_token}` | 200 Session · 401 |
| 2 | GET `/api/projects` | – | 200 `{projects:[{id,name,site_url,created_at,last_run: RunInfo|null}]}` (newest first) |
| 2b | GET `/api/projects/{id}` | – | 200 `{project, pairs: Pair[] (by position), runs: RunInfo[] (newest first)}` · 404 |
| 3 | POST `/api/projects` | `{name, site_url}` | 201 `{id}` · 400 if link missing / not http(s) |
| 4 | POST `/api/pairs/tidy` | `{rough_text, site_url, kind?: "change"}` | 200 `{pair: Draft}` (may contain browser checks with `steps`, never `manual`) · 502 if the AI fails |
| 5 | POST `/api/projects/{id}/suggestions` | – | 200 `{pairs: Draft[]}` (≤5, to show as "suggested"; may contain browser checks with `steps`, never `manual`) · 404 · 502 |
| 6 | POST `/api/projects/{id}/pairs` | Draft + `source`, optional `approved`, `is_priority` (checks may carry `steps`) | 201 `{id, pair: Pair}` · 400 (incl. a forbidden or invalid step) · 404 |
| 7 | PATCH `/api/pairs/{id}` | any of `approved, is_priority, user_does, good_result, request_url, method, request_body, checks` | 200 `{pair: Pair}` · 404 · 409 if editing checks after the pair has run |
| 8 | POST `/api/projects/{id}/runs` | `{kind:"full"}` or `{kind:"changed", pair_ids:[..], other_changes:"..", other_pair_id: id|null}` | 201 `{run: RunInfo, pair_ids:[..]}` (priority first, then position) · 400 no approved pairs |
| 9 | POST `/api/runs/{id}/pairs/{pair_id}` | – | 201 `{rows: Row[2]}` (phone + laptop, each with `via` and `human_reason`); routes every check fetch → browser → person (above); calling twice returns the saved rows |
| 10 | POST `/api/runs/{id}/finish` | – | 200 `{run: RunInfo, points: Point[], changed: Changed[]}` |
| 11 | GET `/api/runs/{id}` | – | 200 `{run, project:{id,name,site_url}, rows: Row[], points: Point[], changed: Changed[], earlier_runs: RunInfo[]}` · 404 |
| 12 | GET `/api/runs/{id}/compare?with={old_id}` | – | 200 `{run, old_run, rows:[{pair_id, position, user_does, device, old_outcome, new_outcome, verdict:"FIXED"|"BROKE"|"same"}]}` |
| 13 | PATCH `/api/result-checks/{id}` | `{passed: true|false}` | 200 `{check: CheckResult}` · 404 / 409 if already answered |
| 14 | GET `/api/health` | – | 200 `{ok:true, browser: bool}` (`browser` = a Browserless key is set; never the key) |

Row order on the results page: priority pairs first, then pairs with any fail, then the rest, by position;
phone before laptop.

`Changed` only appears for `kind:"changed"` runs. `good_now` = "yes" when the pair passes on both phone and
laptop, else "no". `note` = what the builder said they changed (or "Ticked as changed").

Browser flow for a run: door 8 → door 9 once per pair id, in order (table fills live) → door 10 → show points.
