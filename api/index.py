"""Eval Co-pilot API: one FastAPI app holding every /api door (see docs/API.md).

The browser only talks to these doors. The server talks to Supabase as the logged-in user (their
token, so the database's security rules always apply), to Groq for the AI jobs, and to the builder's
live site with plain `requests`.
"""
import ipaddress
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import groq, site, supa  # noqa: E402
from _lib.supa import Db, SupaError, in_list  # noqa: E402

app = FastAPI(title="Eval Co-pilot", docs_url=None, redoc_url=None, openapi_url=None)

DEVICES = ("phone", "laptop")
DOOR_BUDGET = 50  # seconds; Vercel stops a function at 60
CODE_RULES = {"status_ok", "text_has", "text_absent", "count_equals", "min_results"}
RULE_DECIDER = {**{r: "code" for r in CODE_RULES}, "ai_judge": "ai", "manual": "human"}
BLOCKED_WHY = "The site blocked us, so we can't test this."
LOOK_WHY = "This needs your eyes: answer the checks below."
NOT_CHECKED = "Not checked, because the page didn't load."


# ---------------------------------------------------------------- errors

def fail(status: int, message: str):
    raise HTTPException(status_code=status, detail=message)


@app.exception_handler(SupaError)
def _supa_error(_: Request, e: SupaError):
    return JSONResponse(status_code=e.status, content={"detail": str(e)})


@app.exception_handler(groq.GroqError)
def _groq_error(_: Request, e: groq.GroqError):
    return JSONResponse(status_code=502, content={"detail": str(e)})


@app.exception_handler(RequestValidationError)
def _bad_body(_: Request, __: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "Some details are missing or not valid."})


@app.exception_handler(Exception)
def _unexpected(_: Request, __: Exception):
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})


# ---------------------------------------------------------------- helpers

def token_of(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        fail(401, "Please log in.")
    return authorization.split(" ", 1)[1].strip()


def db_for(authorization: str | None) -> Db:
    return Db(token_of(authorization))


async def body_of(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        data = None
    if not isinstance(data, dict):
        fail(400, "Some details are missing or not valid.")
    return data


def text_field(body: dict, name: str, label: str, cap: int = 1000) -> str:
    value = body.get(name)
    if not isinstance(value, str) or not value.strip():
        fail(400, f"Please fill in {label}.")
    return value.strip()[:cap]


def clean_site_url(raw) -> str:
    """A public http(s) link only: no passwords, no local or private addresses."""
    if not isinstance(raw, str) or not raw.strip():
        fail(400, "Please paste the link to your live site.")
    url = raw.strip()
    if "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or not host or "." not in host:
        fail(400, "That doesn't look like a link. It should start with https://")
    if p.username or p.password:
        fail(400, "Please use the public link only, without a username or password in it.")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            fail(400, "Please use the public link of your live site.")
    except ValueError:
        if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
            fail(400, "Please use the public link of your live site.")
    return f"{p.scheme}://{p.netloc}".rstrip("/")


def clean_checks(raw) -> list[dict]:
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        fail(400, "The checks are not valid.")
    out = []
    for c in raw:
        if not isinstance(c, dict) or c.get("rule") not in RULE_DECIDER:
            fail(400, "One of the checks is not valid.")
        expected = c.get("expected")
        expected = None if expected is None else str(expected).strip()[:300] or None
        if c["rule"] in ("text_has", "text_absent", "ai_judge", "manual", "count_equals") and not expected:
            fail(400, "One of the checks needs something to look for.")
        out.append({"decided_by": RULE_DECIDER[c["rule"]], "rule": c["rule"], "expected": expected})
    if len(out) > 10:
        fail(400, "Please keep it to 10 checks per pair.")
    return out


def clean_request(body: dict, partial: bool = False) -> dict:
    """request_url / method / request_body from a pair body. Only same-site paths."""
    out = {}
    if not partial or "request_url" in body:
        url = body.get("request_url") or "/"
        if not isinstance(url, str) or not url.startswith("/") or url.startswith("//"):
            fail(400, "The page to open must start with / (for example /search?q=Solaris).")
        out["request_url"] = url.strip()[:500]
    if not partial or "method" in body:
        method = str(body.get("method") or "GET").upper()
        if method not in ("GET", "POST"):
            fail(400, "Method must be GET or POST.")
        out["method"] = method
    if not partial or "request_body" in body:
        rb = body.get("request_body")
        if rb is not None and not isinstance(rb, (dict, list)):
            fail(400, "The data to send must be JSON.")
        out["request_body"] = rb
    return out


def get_project(db: Db, project_id: str) -> dict:
    p = db.one("projects", id=f"eq.{project_id}", select="id,name,site_url,created_at")
    if not p:
        fail(404, "We couldn't find this site.")
    return p


def get_run(db: Db, run_id: str) -> dict:
    r = db.one("runs", id=f"eq.{run_id}")
    if not r:
        fail(404, "We couldn't find this run.")
    return r


def pairs_with_checks(db: Db, project_id: str) -> list[dict]:
    pairs = db.select("golden_pairs", project_id=f"eq.{project_id}", select="*,checks(*)", order="position.asc")
    for p in pairs:
        p["checks"] = sorted(p.get("checks") or [], key=lambda c: c["created_at"])
    return pairs


def pair_ids_with_results(db: Db, pair_ids: list) -> set:
    if not pair_ids:
        return set()
    rows = db.select("results", golden_pair_id=in_list(pair_ids), select="golden_pair_id")
    return {r["golden_pair_id"] for r in rows}


def run_order(pairs: list[dict]) -> list[dict]:
    return sorted(pairs, key=lambda p: (not p["is_priority"], p["position"]))


def run_info(r: dict) -> dict:
    return {k: r[k] for k in ("id", "project_id", "run_number", "kind", "started_at", "passed", "total")}


# ---------------------------------------------------------------- 14 · health

@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- 1 · login

def _creds(body: dict) -> tuple[str, str]:
    email = body.get("email")
    password = body.get("password")
    if not isinstance(email, str) or "@" not in email or not isinstance(password, str) or not password:
        fail(400, "Please enter your email and password.")
    return email.strip().lower(), password


@app.post("/api/signup")
async def signup(request: Request):
    email, password = _creds(await body_of(request))
    if len(password) < 8:
        fail(400, "Please use at least 8 characters for your password.")
    return supa.signup(email, password)


@app.post("/api/login")
async def login(request: Request):
    email, password = _creds(await body_of(request))
    return supa.login(email, password)


@app.post("/api/refresh")
async def refresh(request: Request):
    token = (await body_of(request)).get("refresh_token")
    if not isinstance(token, str) or not token:
        fail(401, "Please log in again.")
    return supa.refresh(token)


# ---------------------------------------------------------------- 2, 2b, 3 · projects

@app.get("/api/projects")
def list_projects(authorization: str | None = Header(None)):
    db = db_for(authorization)
    projects = db.select("projects", select="id,name,site_url,created_at", order="created_at.desc")
    last = {}
    if projects:
        runs = db.select("runs", project_id=in_list([p["id"] for p in projects]), order="run_number.desc")
        for r in runs:
            last.setdefault(r["project_id"], run_info(r))
    for p in projects:
        p["last_run"] = last.get(p["id"])
    return {"projects": projects}


@app.get("/api/projects/{project_id}")
def read_project(project_id: str, authorization: str | None = Header(None)):
    db = db_for(authorization)
    project = get_project(db, project_id)
    pairs = pairs_with_checks(db, project_id)
    used = pair_ids_with_results(db, [p["id"] for p in pairs])
    for p in pairs:
        p["has_results"] = p["id"] in used
    runs = db.select("runs", project_id=f"eq.{project_id}", order="run_number.desc")
    return {"project": project, "pairs": pairs, "runs": [run_info(r) for r in runs]}


@app.post("/api/projects", status_code=201)
async def create_project(request: Request, authorization: str | None = Header(None)):
    db = db_for(authorization)
    body = await body_of(request)
    site_url = clean_site_url(body.get("site_url"))
    name = (body.get("name") or "").strip()[:120] if isinstance(body.get("name"), str) else ""
    name = name or urlparse(site_url).hostname
    row = db.insert("projects", {"name": name, "site_url": site_url})[0]
    return {"id": row["id"]}


# ---------------------------------------------------------------- 4, 5 · AI drafts

@app.post("/api/pairs/tidy")
async def tidy(request: Request, authorization: str | None = Header(None)):
    supa.get_user(token_of(authorization))  # only logged-in builders may use the AI
    body = await body_of(request)
    rough = text_field(body, "rough_text", "what the user does and what a good result looks like", 3000)
    site_url = clean_site_url(body.get("site_url"))
    if body.get("kind") == "change":
        return {"pair": groq.change_to_pair(rough, site_url)}
    return {"pair": groq.tidy_pair(rough, site_url)}


@app.post("/api/projects/{project_id}/suggestions")
def suggestions(project_id: str, authorization: str | None = Header(None)):
    db = db_for(authorization)
    project = get_project(db, project_id)
    home = site.fetch_home_text(project["site_url"])
    if not home:
        fail(502, "We couldn't read your home page, so we can't suggest pairs right now.")
    return {"pairs": groq.suggest_pairs(home, project["site_url"])}


# ---------------------------------------------------------------- 6, 7 · pairs

def _pair_out(db: Db, pair_id: str) -> dict:
    pair = db.one("golden_pairs", id=f"eq.{pair_id}", select="*,checks(*)")
    if not pair:
        fail(404, "We couldn't find that pair.")
    pair["checks"] = sorted(pair.get("checks") or [], key=lambda c: c["created_at"])
    pair["has_results"] = bool(pair_ids_with_results(db, [pair_id]))
    return pair


@app.post("/api/projects/{project_id}/pairs", status_code=201)
async def create_pair(project_id: str, request: Request, authorization: str | None = Header(None)):
    db = db_for(authorization)
    get_project(db, project_id)
    body = await body_of(request)
    row = {
        "project_id": project_id,
        "user_does": text_field(body, "user_does", "what the user does", 500),
        "good_result": text_field(body, "good_result", "what a good result looks like", 500),
        **clean_request(body),
        "source": "suggested" if body.get("source") == "suggested" else "builder",
        "approved": body.get("approved") is True,
        "is_priority": body.get("is_priority") is True,
    }
    checks = clean_checks(body.get("checks"))
    if not checks:
        fail(400, "Please add at least one check.")
    last = db.one("golden_pairs", project_id=f"eq.{project_id}", select="position", order="position.desc")
    row["position"] = (last["position"] if last else 0) + 1
    pair = db.insert("golden_pairs", row)[0]
    db.insert("checks", [{**c, "golden_pair_id": pair["id"]} for c in checks])
    return {"id": pair["id"], "pair": _pair_out(db, pair["id"])}


@app.patch("/api/pairs/{pair_id}")
async def update_pair(pair_id: str, request: Request, authorization: str | None = Header(None)):
    db = db_for(authorization)
    body = await body_of(request)
    if not db.one("golden_pairs", id=f"eq.{pair_id}", select="id"):
        fail(404, "We couldn't find that pair.")
    values = {}
    for flag in ("approved", "is_priority"):
        if flag in body:
            if not isinstance(body[flag], bool):
                fail(400, "Some details are missing or not valid.")
            values[flag] = body[flag]
    if "user_does" in body:
        values["user_does"] = text_field(body, "user_does", "what the user does", 500)
    if "good_result" in body:
        values["good_result"] = text_field(body, "good_result", "what a good result looks like", 500)
    values.update(clean_request(body, partial=True))
    if "checks" in body:
        checks = clean_checks(body["checks"])
        if not checks:
            fail(400, "Please add at least one check.")
        # Old results point at these checks, so they are locked once the pair has run.
        if pair_ids_with_results(db, [pair_id]):
            fail(409, "Checks are locked after a run, so old results stay comparable. Add a new pair instead.")
        db.delete("checks", golden_pair_id=f"eq.{pair_id}")
        db.insert("checks", [{**c, "golden_pair_id": pair_id} for c in checks])
    if values:
        db.update("golden_pairs", values, id=f"eq.{pair_id}")
    return {"pair": _pair_out(db, pair_id)}


# ---------------------------------------------------------------- 8 · start a run

@app.post("/api/projects/{project_id}/runs", status_code=201)
async def create_run(project_id: str, request: Request, authorization: str | None = Header(None)):
    db = db_for(authorization)
    get_project(db, project_id)
    body = await body_of(request)
    kind = body.get("kind")
    if kind not in ("full", "changed"):
        fail(400, "Pick a full run or a re-run of changed pairs.")
    approved = {p["id"]: p for p in db.select(
        "golden_pairs", project_id=f"eq.{project_id}", approved="is.true", select="id,position,is_priority")}
    if kind == "full":
        chosen = list(approved.values())
    else:
        ids = body.get("pair_ids") or []
        other_pair_id = body.get("other_pair_id")
        if other_pair_id and other_pair_id not in ids:
            ids = [*ids, other_pair_id]
        if not isinstance(ids, list) or not ids:
            fail(400, "Tick at least one pair you changed.")
        if any(i not in approved for i in ids):
            fail(400, "Only approved pairs of this site can run.")
        chosen = [approved[i] for i in dict.fromkeys(ids)]
    if not chosen:
        fail(400, "Approve at least one pair before running.")

    run = None
    for _ in range(3):  # two runs started at once can race for the same number
        last = db.one("runs", project_id=f"eq.{project_id}", select="run_number", order="run_number.desc")
        try:
            run = db.insert("runs", {"project_id": project_id, "kind": kind,
                                     "run_number": (last["run_number"] if last else 0) + 1})[0]
            break
        except SupaError as e:
            if e.code != "23505":
                raise
    if not run:
        fail(409, "Another run just started. Please try again.")

    if kind == "changed":
        note = (body.get("other_changes") or "").strip()[:2000] if isinstance(body.get("other_changes"), str) else ""
        other_pair_id = body.get("other_pair_id")
        changes = [{"run_id": run["id"], "golden_pair_id": p["id"], "note": "Ticked as changed"}
                   for p in chosen if p["id"] != other_pair_id]
        if other_pair_id or note:
            changes.append({"run_id": run["id"], "golden_pair_id": other_pair_id or None,
                            "note": note or "Other change"})
        db.insert("changes", changes)
    return {"run": run_info(run), "pair_ids": [p["id"] for p in run_order(chosen)]}


# ---------------------------------------------------------------- 9 · test one pair

def _judge_device(pair: dict, checks: list[dict], reply: site.SiteReply, budget: float) -> dict:
    """Decide every check for one device. Returns {outcome, rows:[{check_id, passed, why}]}."""
    if reply.blocked:
        return {"outcome": "cant_test", "rows": [{"check_id": c["id"], "passed": None, "why": BLOCKED_WHY}
                                                for c in checks]}
    page_failed = reply.error is not None or reply.status_code is None or reply.status_code >= 400
    decided, failed_code, ai_checks = {}, [], []
    if page_failed:
        # The page didn't load: one check carries the reason (the status check if there is one),
        # the other automatic checks are marked not checked, manual checks still wait for a human.
        reason = reply.error or site.run_code_check("status_ok", None, reply)[1]
        auto = [c for c in checks if c["rule"] != "manual"]
        carrier = next((c for c in auto if c["rule"] == "status_ok"), auto[0] if auto else None)
        for c in checks:
            if c["rule"] == "manual":
                decided[c["id"]] = {"passed": None, "why": f"You look: {c['expected']}"}
            elif c is carrier:
                decided[c["id"]] = {"passed": False, "why": reason}
                failed_code.append({**c, "rule": "status_ok", "expected": None, "detail": reason})
            else:
                decided[c["id"]] = {"passed": False, "why": NOT_CHECKED}
    else:
        for c in checks:
            if c["rule"] == "manual":
                decided[c["id"]] = {"passed": None, "why": f"You look: {c['expected']}"}
            elif c["rule"] in CODE_RULES:
                ok, detail = site.run_code_check(c["rule"], c["expected"], reply)
                decided[c["id"]] = {"passed": ok, "why": detail}
                if not ok:
                    failed_code.append({**c, "detail": detail})
            else:
                ai_checks.append(c)
    if (ai_checks or failed_code) and budget > 4:
        decided.update(groq.judge(reply.text, pair, ai_checks, failed_code, timeout=budget))
    for c in ai_checks:
        decided.setdefault(c["id"], {"passed": None, "why": groq.AI_UNSURE})

    rows = [{"check_id": c["id"], **decided[c["id"]]} for c in checks if c["id"] in decided]
    values = [r["passed"] for r in rows]
    if any(v is False for v in values):
        outcome = "fail"
    elif any(v is True for v in values):
        outcome = "pass"
    else:
        outcome = "cant_test"  # every check needs a human (or the AI couldn't judge any)
    return {"outcome": outcome, "rows": rows}


def _focus_words(checks: list[dict]) -> list[str]:
    return [c["expected"] for c in checks if c["rule"] in ("text_has", "text_absent") and c["expected"]]


def _row_why(outcome: str, checks: list[dict]) -> str:
    if outcome == "pass":
        return ""
    for c in checks:
        if c["passed"] is False and c.get("why"):
            return c["why"]
    if any(c.get("why") == BLOCKED_WHY for c in checks):
        return BLOCKED_WHY
    if any(c.get("why") == groq.AI_UNSURE for c in checks):
        return "The AI couldn't decide. Please answer the checks below."
    return LOOK_WHY


def build_rows(db: Db, run_id: str, pair_id: str | None = None) -> list[dict]:
    """Results of a run (optionally one pair) in the Row shape, ordered for the results table."""
    params = {"run_id": f"eq.{run_id}",
              "select": "*,golden_pairs(position,user_does,good_result,is_priority),"
                        "result_checks(id,check_id,passed,why,checks(decided_by,rule,expected,created_at))"}
    if pair_id:
        params["golden_pair_id"] = f"eq.{pair_id}"
    results = db.select("results", **params)
    rows = []
    for r in results:
        g = r.get("golden_pairs") or {}
        checks = []
        for rc in sorted(r.get("result_checks") or [], key=lambda x: (x.get("checks") or {}).get("created_at") or ""):
            c = rc.get("checks") or {}
            checks.append({"id": rc["id"], "check_id": rc["check_id"], "decided_by": c.get("decided_by"),
                           "rule": c.get("rule"), "expected": c.get("expected"),
                           "passed": rc["passed"], "why": rc["why"]})
        rows.append({
            "result_id": r["id"], "run_id": r["run_id"], "pair_id": r["golden_pair_id"],
            "position": g.get("position"), "user_does": g.get("user_does"), "good_result": g.get("good_result"),
            "is_priority": bool(g.get("is_priority")), "device": r["device"], "status_code": r["status_code"],
            "outcome": r["outcome"], "what_site_said": r["what_site_said"],
            "why": _row_why(r["outcome"], checks), "checks": checks,
        })
    failing = {x["pair_id"] for x in rows if x["outcome"] == "fail"}
    rows.sort(key=lambda x: (not x["is_priority"], x["pair_id"] not in failing, x["position"] or 0,
                             DEVICES.index(x["device"])))
    return rows


@app.post("/api/runs/{run_id}/pairs/{pair_id}", status_code=201)
def run_pair(run_id: str, pair_id: str, authorization: str | None = Header(None)):
    started = time.monotonic()
    db = db_for(authorization)
    run = get_run(db, run_id)
    pair = db.one("golden_pairs", id=f"eq.{pair_id}", project_id=f"eq.{run['project_id']}", select="*,checks(*)")
    if not pair:
        fail(404, "We couldn't find that pair in this site.")
    if not pair["approved"]:
        fail(400, "This pair isn't approved yet.")
    done = {r["device"] for r in db.select("results", run_id=f"eq.{run_id}", golden_pair_id=f"eq.{pair_id}",
                                           select="device")}
    todo = [d for d in DEVICES if d not in done]
    if todo:
        project = get_project(db, run["project_id"])
        checks = sorted(pair.get("checks") or [], key=lambda c: c["created_at"])
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = dict(zip(todo, pool.map(
                lambda d: site.fetch_pair(project["site_url"], pair["request_url"] or "/", pair["method"],
                                          pair["request_body"], d), todo)))
            budget = DOOR_BUDGET - (time.monotonic() - started)
            verdicts = dict(zip(todo, pool.map(lambda d: _judge_device(pair, checks, replies[d], budget), todo)))
        for d in todo:
            reply, verdict = replies[d], verdicts[d]
            try:
                result = db.insert("results", {
                    "run_id": run_id, "golden_pair_id": pair_id, "device": d,
                    "status_code": reply.status_code, "outcome": verdict["outcome"],
                    "what_site_said": site.excerpt(reply, _focus_words(checks))[:500],
                })[0]
            except SupaError as e:
                if e.code == "23505":  # saved by a parallel call already: keep that one
                    continue
                raise
            if verdict["rows"]:
                db.insert("result_checks", [{"result_id": result["id"], "check_id": x["check_id"],
                                             "passed": x["passed"], "why": (x["why"] or "")[:300]}
                                            for x in verdict["rows"]])
    rows = sorted(build_rows(db, run_id, pair_id), key=lambda x: DEVICES.index(x["device"]))
    return {"rows": rows}


# ---------------------------------------------------------------- 10, 11 · finish + read a run

def pick_worst(rows: list[dict]) -> list[dict]:
    """Code picks up to 3 failed results: priority first, then failed on both devices, then by position.
    Different pairs come before a second device of the same pair."""
    fails = [r for r in rows if r["outcome"] == "fail"]
    fail_count = {}
    for r in fails:
        fail_count[r["pair_id"]] = fail_count.get(r["pair_id"], 0) + 1
    fails.sort(key=lambda r: (not r["is_priority"], fail_count[r["pair_id"]] < 2, r["position"] or 0,
                              DEVICES.index(r["device"])))
    picked, seen = [], set()
    for r in fails:
        if r["pair_id"] not in seen:
            picked.append(r)
            seen.add(r["pair_id"])
    for r in fails:
        if r not in picked:
            picked.append(r)
    return picked[:3]


def read_points(db: Db, run_id: str, rows: list[dict]) -> list[dict]:
    by_id = {r["result_id"]: r for r in rows}
    out = []
    for p in db.select("diagnosis_points", run_id=f"eq.{run_id}", order="rank.asc"):
        r = by_id.get(p["result_id"], {})
        out.append({"rank": p["rank"], "result_id": p["result_id"], "pair_id": r.get("pair_id"),
                    "position": r.get("position"), "user_does": r.get("user_does"), "device": r.get("device"),
                    "explanation": p["explanation"], "what_site_said": r.get("what_site_said")})
    return out


def read_changed(db: Db, run: dict, rows: list[dict]) -> list[dict]:
    if run["kind"] != "changed":
        return []
    out = []
    for ch in db.select("changes", run_id=f"eq.{run['id']}", order="created_at.asc"):
        pid = ch["golden_pair_id"]
        if not pid:
            continue
        mine = {r["device"]: r for r in rows if r["pair_id"] == pid}
        any_row = next(iter(mine.values()), {})
        phone = mine.get("phone", {}).get("outcome")
        laptop = mine.get("laptop", {}).get("outcome")
        out.append({"pair_id": pid, "position": any_row.get("position"), "user_does": any_row.get("user_does"),
                    "note": ch["note"], "phone": phone, "laptop": laptop,
                    "good_now": "yes" if phone == "pass" and laptop == "pass" else "no"})
    return out


@app.post("/api/runs/{run_id}/finish")
def finish_run(run_id: str, authorization: str | None = Header(None)):
    db = db_for(authorization)
    run = get_run(db, run_id)
    rows = build_rows(db, run_id)
    passed, total = sum(r["outcome"] == "pass" for r in rows), len(rows)
    run = db.update("runs", {"passed": passed, "total": total}, id=f"eq.{run_id}")[0]
    if not db.select("diagnosis_points", run_id=f"eq.{run_id}", select="id"):
        worst = pick_worst(rows)
        if worst:
            explained = groq.diagnose([{
                "result_id": r["result_id"], "user_does": r["user_does"], "good_result": r["good_result"],
                "device": r["device"], "status_code": r["status_code"], "what_site_said": r["what_site_said"],
                "failed_checks": [{"rule": c["rule"], "expected": c["expected"], "why": c["why"]}
                                  for c in r["checks"] if c["passed"] is False],
            } for r in worst], timeout=40)
            try:
                db.insert("diagnosis_points", [
                    {"run_id": run_id, "result_id": r["result_id"], "rank": i + 1,
                     "explanation": explained.get(r["result_id"]) or r["why"] or "This failed."}
                    for i, r in enumerate(worst)])
            except SupaError as e:
                if e.code != "23505":  # a parallel finish already saved them
                    raise
    return {"run": run_info(run), "points": read_points(db, run_id, rows), "changed": read_changed(db, run, rows)}


@app.get("/api/runs/{run_id}")
def read_run(run_id: str, authorization: str | None = Header(None)):
    db = db_for(authorization)
    run = get_run(db, run_id)
    project = get_project(db, run["project_id"])
    rows = build_rows(db, run_id)
    earlier = db.select("runs", project_id=f"eq.{run['project_id']}", run_number=f"lt.{run['run_number']}",
                        order="run_number.desc")
    return {"run": run_info(run), "project": {k: project[k] for k in ("id", "name", "site_url")}, "rows": rows,
            "points": read_points(db, run_id, rows), "changed": read_changed(db, run, rows),
            "earlier_runs": [run_info(r) for r in earlier]}


# ---------------------------------------------------------------- 12 · compare

def verdict(old: str | None, new: str) -> str:
    if old == "fail" and new == "pass":
        return "FIXED"
    if old == "pass" and new == "fail":
        return "BROKE"
    return "same"


@app.get("/api/runs/{run_id}/compare")
def compare(run_id: str, request: Request, authorization: str | None = Header(None)):
    db = db_for(authorization)
    run = get_run(db, run_id)
    old_id = request.query_params.get("with")
    old_run = None
    if old_id:
        old_run = get_run(db, old_id)
        if old_run["project_id"] != run["project_id"]:
            fail(400, "You can only compare runs of the same site.")
        old_runs = [old_run]
    else:  # each pair against the most recent earlier run that tested it
        old_runs = db.select("runs", project_id=f"eq.{run['project_id']}", run_number=f"lt.{run['run_number']}",
                             order="run_number.desc")
    new_rows = build_rows(db, run_id)
    old_results = {}
    if old_runs:
        number = {r["id"]: r["run_number"] for r in old_runs}
        for r in db.select("results", run_id=in_list(list(number)), select="run_id,golden_pair_id,device,outcome"):
            key = (r["golden_pair_id"], r["device"])
            if key not in old_results or number[r["run_id"]] > number[old_results[key]["run_id"]]:
                old_results[key] = r
    rows = []
    for r in new_rows:
        old = old_results.get((r["pair_id"], r["device"]))
        rows.append({"pair_id": r["pair_id"], "position": r["position"], "user_does": r["user_does"],
                     "device": r["device"], "old_outcome": old["outcome"] if old else None,
                     "new_outcome": r["outcome"], "verdict": verdict(old["outcome"] if old else None, r["outcome"])})
    return {"run": run_info(run), "old_run": run_info(old_run) if old_run else None, "rows": rows}


# ---------------------------------------------------------------- 13 · a human answers a manual check

@app.patch("/api/result-checks/{check_id}")
async def answer_check(check_id: str, request: Request, authorization: str | None = Header(None)):
    db = db_for(authorization)
    passed = (await body_of(request)).get("passed")
    if not isinstance(passed, bool):
        fail(400, "Answer with looks right or looks wrong.")
    row = db.one("result_checks", id=f"eq.{check_id}", select="id,passed,why,check_id,checks(decided_by,rule,expected)")
    if not row:
        fail(404, "We couldn't find that check.")
    if row["passed"] is not None:
        fail(409, "This check already has an answer.")
    why = "You said it looks right." if passed else "You said it looks wrong."
    updated = db.update("result_checks", {"passed": passed, "why": why}, id=f"eq.{check_id}")
    if not updated:
        fail(409, "This check already has an answer.")
    c = row.get("checks") or {}
    return {"check": {"id": check_id, "check_id": row["check_id"], "decided_by": c.get("decided_by"),
                      "rule": c.get("rule"), "expected": c.get("expected"), "passed": passed, "why": why}}
