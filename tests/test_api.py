"""End-to-end tests of the Eval Co-pilot API (api/index.py) through FastAPI's TestClient.

Nothing leaves this machine:
  * Supabase  -> tests/fake_db.py (in-memory tables, the SQL file's rules and RLS)
  * the site  -> FakeSite below (scripted pages; "broken" / "fixed" versions of the builder's shop)
  * Groq      -> FakeGroq below (fixed drafts, scripted judge / diagnose)
`site.run_code_check` and `site.excerpt` stay REAL, so code checks are really decided on the fake pages.

Tests marked xfail("BUG: ...") describe real problems in api/index.py; they should start passing once fixed.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT / "api"), str(ROOT)):  # index.py wants api/ on the path; the repo root is for `api._lib`
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi.testclient import TestClient  # noqa: E402

import index  # noqa: E402  (api/index.py)
from fake_db import USER_A, USER_B, FakeDb, FakeStore, db_factory  # noqa: E402

site = index.site  # the very modules index.py uses, so SiteReply / SupaError / GroqError are the real classes
groq = index.groq
SupaError = index.SupaError
REAL_JUDGE = groq.judge

TOK_A, TOK_B = "tok-A", "tok-B"
SITE_URL = "https://shop.example.com"
BLOCKED_WHY = "The site blocked us, so we can't test this."
NOT_CHECKED = "Not checked, because the page didn't load."
UNSURE_ROW_WHY = "The AI couldn't decide. Please answer the checks below."
LOOK_WHY = "This needs your eyes: answer the checks below."

# ---------------------------------------------------------------- shapes from docs/API.md

RUN_INFO = {"id", "project_id", "run_number", "kind", "started_at", "passed", "total"}
PAIR = {"id", "project_id", "position", "user_does", "good_result", "request_url", "method", "request_body",
        "source", "approved", "is_priority", "created_at", "checks", "has_results"}
CHECK = {"id", "decided_by", "rule", "expected"}  # docs list these four; the API may send more
ROW = {"result_id", "run_id", "pair_id", "position", "user_does", "good_result", "is_priority", "device",
       "status_code", "outcome", "what_site_said", "why", "checks"}
CHECK_RESULT = {"id", "check_id", "decided_by", "rule", "expected", "passed", "why"}
POINT = {"rank", "result_id", "pair_id", "position", "user_does", "device", "explanation", "what_site_said"}
CHANGED = {"pair_id", "position", "user_does", "note", "phone", "laptop", "good_now"}
SESSION = {"access_token", "refresh_token", "expires_at", "user"}
DECIDER = {"status_ok": "code", "text_has": "code", "text_absent": "code", "count_equals": "code",
           "min_results": "code", "ai_judge": "ai", "manual": "human"}


def is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return isinstance(value, str)
    except ValueError:
        return False


def check_run_info(info: dict):
    assert set(info) == RUN_INFO
    assert is_uuid(info["id"]) and is_uuid(info["project_id"])
    assert isinstance(info["run_number"], int) and info["kind"] in ("full", "changed")
    assert isinstance(info["started_at"], str) and isinstance(info["passed"], int) and isinstance(info["total"], int)


def check_pair(pair: dict):
    assert set(pair) == PAIR
    assert is_uuid(pair["id"]) and pair["method"] in ("GET", "POST") and pair["source"] in ("builder", "suggested")
    assert isinstance(pair["approved"], bool) and isinstance(pair["is_priority"], bool)
    assert isinstance(pair["has_results"], bool) and isinstance(pair["position"], int)
    assert pair["request_body"] is None or isinstance(pair["request_body"], (dict, list))
    for c in pair["checks"]:
        assert CHECK <= set(c) and is_uuid(c["id"]) and c["decided_by"] == DECIDER[c["rule"]]


def check_row(row: dict):
    assert set(row) == ROW
    assert is_uuid(row["result_id"]) and is_uuid(row["run_id"]) and is_uuid(row["pair_id"])
    assert row["device"] in ("phone", "laptop") and row["outcome"] in ("pass", "fail", "cant_test")
    assert row["status_code"] is None or isinstance(row["status_code"], int)
    assert isinstance(row["why"], str) and isinstance(row["what_site_said"], str) and isinstance(row["is_priority"], bool)
    if row["outcome"] == "pass":
        assert row["why"] == ""
    else:
        assert row["why"]
    for c in row["checks"]:
        assert set(c) == CHECK_RESULT
        assert c["passed"] in (True, False, None) and isinstance(c["why"], str)


def check_point(p: dict):
    assert set(p) == POINT and 1 <= p["rank"] <= 3 and p["explanation"]


def err(resp, status: int) -> str:
    """The error contract: right status and exactly {"detail": "plain words"}."""
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert list(body) == ["detail"] and isinstance(body["detail"], str) and body["detail"]
    return body["detail"]


def ok(resp, status: int = 200):
    assert resp.status_code == status, resp.text
    return resp.json()


# ---------------------------------------------------------------- fake site

class FakeResp:
    """Just enough of requests.Response for site._reply_from_response (the real HTML/JSON parsing)."""

    def __init__(self, status: int, body, ctype: str = "text/html"):
        self.status_code = status
        self.text = body if isinstance(body, str) else json.dumps(body)
        self.headers = {"Content-Type": "application/json" if not isinstance(body, str) else ctype}


def html(title: str, body: str) -> str:
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>"


PAGES = {
    "/": html("Example Shop", "<h1>Welcome to Example Shop</h1><a href='/collections/all'>Shop all</a>"),
    "/search?q=Solaris": html(
        "Search: Solaris",
        '<h1>Search results for Solaris</h1><a href="/products/solaris">Solaris</a> '
        '<a href="/products/solaris-mini">Solaris Mini</a>'),
    "/collections/cabinet-lights": html(
        "Cabinet Lights",
        "<h1>Cabinet Lights</h1><a href='/products/walkie'>Walkie</a> <a href='/products/walkie-x'>Walkie X</a> "
        "<a href='/products/comfort'>Comfort</a>"),
    "/pages/shipping": html("Shipping", "<p>Free shipping on orders over $50</p>"),
}


class FakeSite:
    """Scripted stand-in for site.fetch_pair. `version` switches the builder's shop between "broken" and
    "fixed": broken puts FIVE lamps in the laptop's cart (the phone gets one), fixed puts one everywhere."""

    def __init__(self):
        self.version = "broken"
        self.calls: list[tuple] = []
        self.overrides: dict[str, tuple[int, str]] = {}  # request_url -> (status, body)

    def cart(self, count: int) -> dict:
        return {"token": "t", "item_count": count, "currency": "EUR", "total_price": 7900 * count,
                "items": [{"product_title": "Solaris", "variant_title": "Black", "quantity": count,
                           "final_price": 7900}]}

    def fetch_pair(self, site_url, request_url, method, request_body, device):
        self.calls.append((device, method, request_url, request_body))
        url = site.full_url(site_url, request_url)
        path = request_url.split("?")[0]

        def reply(resp):
            return site._reply_from_response(device, url, resp)

        if request_url in self.overrides:
            status, body = self.overrides[request_url]
            return reply(FakeResp(status, body))
        if method == "POST" and path.startswith("/cart/"):
            count = 5 if (self.version == "broken" and device == "laptop") else 1
            r = reply(FakeResp(200, self.cart(count)))
            r.summary = site.cart_summary(r.json)
            return r
        if path == "/slow":
            return site.SiteReply(device=device, url=url, error=site.TIMEOUT_MESSAGE)
        if path == "/blocked":
            return reply(FakeResp(403, "Forbidden"))
        if path == "/broken":
            return reply(FakeResp(404, html("Not found", "<p>Page not found</p>")))
        if request_url in PAGES:
            return reply(FakeResp(200, PAGES[request_url]))
        return reply(FakeResp(404, html("Not found", "<p>Page not found</p>")))

    def calls_to(self, request_url: str) -> list[tuple]:
        return [c for c in self.calls if c[2] == request_url]


# ---------------------------------------------------------------- fake groq

def draft(user_does: str, **over) -> dict:
    d = {"user_does": user_does, "good_result": "It works.", "request_url": "/search?q=Solaris",
         "method": "GET", "request_body": None,
         "checks": [{"decided_by": "code", "rule": "status_ok", "expected": None},
                    {"decided_by": "code", "rule": "text_has", "expected": "Solaris"}]}
    d.update(over)
    return d


class FakeGroq:
    """Fixed drafts. `mode` steers judge: "normal" | "unsure" (AI_UNSURE answers) | "empty" (answers nothing)."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.mode = "normal"
        self.error: Exception | None = None

    def _maybe_fail(self):
        if self.error:
            raise self.error

    def tidy_pair(self, rough_text, site_url):
        self.calls.append(("tidy_pair", rough_text, site_url))
        self._maybe_fail()
        return draft(f"Tidy: {rough_text}")

    def change_to_pair(self, note, site_url):
        self.calls.append(("change_to_pair", note, site_url))
        self._maybe_fail()
        return draft(f"Changed: {note}", request_url="/pages/shipping")

    def suggest_pairs(self, home_text, site_url):
        self.calls.append(("suggest_pairs", home_text, site_url))
        self._maybe_fail()
        return [draft(f"Suggested {i}") for i in range(1, 6)]

    def judge(self, page_text, pair, ai_checks, failed_code_checks, timeout=None):
        self.calls.append(("judge", pair["id"], [c["id"] for c in ai_checks], [c["id"] for c in failed_code_checks]))
        out = {}
        for c in ai_checks:
            if self.mode == "unsure":
                out[c["id"]] = {"passed": None, "why": groq.AI_UNSURE}
            elif self.mode == "normal":
                seen = "solaris" in page_text.lower()
                out[c["id"]] = {"passed": seen, "why": "AI: looks right." if seen else "AI: Solaris is not on the page."}
        for c in failed_code_checks:
            out[c["id"]] = {"passed": False, "why": f"AI: {c['detail']}"}
        return out

    def diagnose(self, items, timeout=None):
        self.calls.append(("diagnose", items, timeout))
        return {i["result_id"]: f"explanation for {i['result_id']}" for i in items}

    def called(self, name: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == name]


# ---------------------------------------------------------------- fake login

def session_for(email: str) -> dict:
    return {"access_token": TOK_A, "refresh_token": "ref-A", "expires_at": 1893456000,
            "user": {"id": USER_A, "email": email}}


# ---------------------------------------------------------------- wiring

class Api:
    def __init__(self, client: TestClient):
        self.c = client

    def call(self, method, path, tok=TOK_A, **kw):
        headers = dict(kw.pop("headers", {}))
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        return self.c.request(method, path, headers=headers, **kw)

    def get(self, path, tok=TOK_A, **kw):
        return self.call("GET", path, tok, **kw)

    def post(self, path, json=None, tok=TOK_A, **kw):
        return self.call("POST", path, tok, json=json, **kw)

    def patch(self, path, json=None, tok=TOK_A, **kw):
        return self.call("PATCH", path, tok, json=json, **kw)


@pytest.fixture
def env(monkeypatch):
    store, fsite, fgroq, auth_calls = FakeStore(), FakeSite(), FakeGroq(), []

    def fake_get_user(token):
        info = store.user_info(token)
        if not info:
            raise SupaError(401, "Please log in again.")
        return info

    def fake_signup(email, password):
        auth_calls.append(("signup", email, password))
        if email == "confirm@example.com":
            raise SupaError(409, "Check your email to confirm your account, then log in.")
        return session_for(email)

    def fake_login(email, password):
        auth_calls.append(("login", email, password))
        if password != "correct-horse":
            raise SupaError(401, "That email and password don't match.")
        return session_for(email)

    def fake_refresh(refresh_token):
        auth_calls.append(("refresh", refresh_token))
        if refresh_token != "ref-A":
            raise SupaError(401, "Please log in again.")
        return session_for("a@example.com")

    monkeypatch.setattr(index, "Db", db_factory(store))
    monkeypatch.setattr(index.supa, "get_user", fake_get_user)
    monkeypatch.setattr(index.supa, "signup", fake_signup)
    monkeypatch.setattr(index.supa, "login", fake_login)
    monkeypatch.setattr(index.supa, "refresh", fake_refresh)
    monkeypatch.setattr(site, "fetch_pair", fsite.fetch_pair)  # run_code_check / excerpt stay real
    for name in ("tidy_pair", "change_to_pair", "suggest_pairs", "judge", "diagnose"):
        monkeypatch.setattr(groq, name, getattr(fgroq, name))
    client = TestClient(index.app, raise_server_exceptions=False)
    return SimpleNamespace(api=Api(client), store=store, site=fsite, groq=fgroq, auth=auth_calls, mp=monkeypatch)


@pytest.fixture
def api(env):
    return env.api


# ---------------------------------------------------------------- scenario builders

def chk(rule, expected=None):
    return {"decided_by": DECIDER[rule], "rule": rule, "expected": expected}


def new_project(api, tok=TOK_A, site_url=SITE_URL, name=None) -> str:
    body = {"site_url": site_url}
    if name:
        body["name"] = name
    return ok(api.post("/api/projects", body, tok=tok), 201)["id"]


def new_pair(api, project_id, user_does, request_url, checks, tok=TOK_A, **over) -> dict:
    body = {"user_does": user_does, "good_result": f"Good: {user_does}", "request_url": request_url,
            "method": "GET", "request_body": None, "checks": checks, **over}
    return ok(api.post(f"/api/projects/{project_id}/pairs", body, tok=tok), 201)["pair"]


# name -> (request_url, checks, extra fields). Positions follow this order (1..8).
SCENARIO = {
    "search": ("/search?q=Solaris", [chk("status_ok"), chk("min_results", "2"), chk("text_has", "Solaris"),
                                      chk("ai_judge", "Does the page show the Solaris lamp?")], {}),
    "collection": ("/collections/cabinet-lights", [chk("status_ok"), chk("text_has", "Cabinet Lights"),
                                                   chk("manual", "Do the product photos look right?")], {}),
    "blocked": ("/blocked", [chk("status_ok"), chk("text_has", "Solaris")], {}),
    "cart": ("/cart/add.js", [chk("status_ok"), chk("count_equals", "item_count=1")],
             {"method": "POST", "request_body": {"items": [{"handle": "solaris", "quantity": 1}]},
              "is_priority": True}),
    "dead": ("/broken", [chk("status_ok"), chk("text_has", "Solaris"), chk("text_absent", "Oops")], {}),
    "look": ("/", [chk("manual", "Does the home page look friendly?")], {}),
    "slow": ("/slow", [chk("status_ok"), chk("text_has", "Solaris")], {}),
    "draft": ("/", [chk("status_ok")], {"approved": False}),  # never approved: must stay out of runs
}


@pytest.fixture
def world(api):
    """Project of user A with 8 pairs (7 approved, `cart` is the priority one). Nothing has run yet."""
    pid = new_project(api, name="Example Shop")
    ids, pairs = {}, {}
    for name, (url, checks, extra) in SCENARIO.items():
        pair = new_pair(api, pid, name.capitalize(), url, checks, **{"approved": True, **extra})
        ids[name], pairs[name] = pair["id"], pair
    names = {v: k for k, v in ids.items()}
    return SimpleNamespace(pid=pid, ids=ids, pairs=pairs, names=names)


def run_everything(api, w, body, tok=TOK_A) -> SimpleNamespace:
    """Door 8, door 9 once per pair id (in the order given), door 10."""
    started = ok(api.post(f"/api/projects/{w.pid}/runs", body, tok=tok), 201)
    run_id, rows = started["run"]["id"], {}
    for pair_id in started["pair_ids"]:
        rows[w.names[pair_id]] = ok(api.post(f"/api/runs/{run_id}/pairs/{pair_id}", tok=tok), 201)["rows"]
    done = ok(api.post(f"/api/runs/{run_id}/finish", tok=tok))
    return SimpleNamespace(id=run_id, started=started, rows=rows, done=done, info=done["run"])


@pytest.fixture
def ran(api, world):
    """Run 1: a full run on the broken shop, tested and finished."""
    return run_everything(api, world, {"kind": "full"})


@pytest.fixture
def rerun(env, world, ran):
    """Run 2: the builder fixed the cart; a re-run of the changed pair plus a brand-new pair."""
    api = env.api
    env.site.version = "fixed"
    banner = new_pair(api, world.pid, "Reads the banner", "/pages/shipping", [chk("text_has", "Free shipping")],
                      approved=True)
    world.ids["banner"], world.names[banner["id"]] = banner["id"], "banner"
    r2 = run_everything(api, world, {"kind": "changed", "pair_ids": [world.ids["cart"]],
                                     "other_changes": "I changed the shipping banner",
                                     "other_pair_id": banner["id"]})
    return r2


def pair_order(world, rows) -> list[str]:
    seen = []
    for r in rows:
        name = world.names[r["pair_id"]]
        if name not in seen:
            seen.append(name)
    return seen


# ================================================================ health + login

def test_health(api):
    assert ok(api.get("/api/health", tok=None)) == {"ok": True}


def test_login_signup_refresh_pass_through(env, api):
    s = ok(api.post("/api/login", {"email": " A@Example.com ", "password": "correct-horse"}, tok=None))
    assert set(s) == SESSION and set(s["user"]) == {"id", "email"} and s["user"]["email"] == "a@example.com"
    s = ok(api.post("/api/signup", {"email": "new@example.com", "password": "longenough"}, tok=None))
    assert set(s) == SESSION
    s = ok(api.post("/api/refresh", {"refresh_token": "ref-A"}, tok=None))
    assert set(s) == SESSION
    assert env.auth == [("login", "a@example.com", "correct-horse"), ("signup", "new@example.com", "longenough"),
                        ("refresh", "ref-A")]


def test_login_wrong_password_is_401(api):
    assert err(api.post("/api/login", {"email": "a@example.com", "password": "nope"}, tok=None), 401)


def test_signup_needs_confirmation_is_409(api):
    assert err(api.post("/api/signup", {"email": "confirm@example.com", "password": "longenough"}, tok=None), 409)


@pytest.mark.parametrize("path,body", [
    ("/api/login", {}), ("/api/login", {"email": "no-at-sign", "password": "x"}),
    ("/api/login", {"email": "a@example.com"}), ("/api/signup", {"email": "a@example.com", "password": "short"}),
    ("/api/signup", {"email": "a@example.com", "password": ""}),
])
def test_login_signup_bad_input_is_400(env, api, path, body):
    err(api.post(path, body, tok=None), 400)
    assert env.auth == []  # never reached Supabase


def test_refresh_without_or_with_bad_token_is_401(api):
    err(api.post("/api/refresh", {}, tok=None), 401)
    err(api.post("/api/refresh", {"refresh_token": "stale"}, tok=None), 401)


def test_non_json_body_is_400_with_detail(api):
    resp = api.call("POST", "/api/login", tok=None, content="not json", headers={"Content-Type": "application/json"})
    assert err(resp, 400) == "Some details are missing or not valid."
    assert err(api.post("/api/login", ["a", "b"], tok=None), 400)


AUTH_DOORS = [
    ("GET", "/api/projects"), ("GET", "/api/projects/{id}"), ("POST", "/api/projects"),
    ("POST", "/api/pairs/tidy"), ("POST", "/api/projects/{id}/suggestions"), ("POST", "/api/projects/{id}/pairs"),
    ("PATCH", "/api/pairs/{id}"), ("POST", "/api/projects/{id}/runs"), ("POST", "/api/runs/{id}/pairs/{id}"),
    ("POST", "/api/runs/{id}/finish"), ("GET", "/api/runs/{id}"), ("GET", "/api/runs/{id}/compare"),
    ("PATCH", "/api/result-checks/{id}"),
]


@pytest.mark.parametrize("method,path", AUTH_DOORS)
def test_missing_token_is_401_everywhere(api, method, path):
    path = path.replace("{id}", str(uuid.uuid4()))
    assert err(api.call(method, path, tok=None, json={}), 401) == "Please log in."


@pytest.mark.parametrize("method,path", AUTH_DOORS)
def test_malformed_authorization_header_is_401(api, method, path):
    path = path.replace("{id}", str(uuid.uuid4()))
    resp = api.call(method, path, tok=None, json={}, headers={"Authorization": "Basic abc"})
    err(resp, 401)


def test_expired_or_unknown_token_is_401(api):
    assert err(api.get("/api/projects", tok="tok-expired"), 401)
    assert err(api.post("/api/pairs/tidy", {"rough_text": "x", "site_url": SITE_URL}, tok="tok-expired"), 401)


# ================================================================ projects

def test_create_project_201_and_listed(api):
    resp = api.post("/api/projects", {"name": "My Shop", "site_url": "https://shop.example.com/"})
    assert resp.status_code == 201 and set(resp.json()) == {"id"} and is_uuid(resp.json()["id"])
    listed = ok(api.get("/api/projects"))["projects"]
    assert len(listed) == 1
    assert set(listed[0]) == {"id", "name", "site_url", "created_at", "last_run"}
    assert listed[0]["name"] == "My Shop" and listed[0]["site_url"] == "https://shop.example.com"
    assert listed[0]["last_run"] is None


def test_create_project_cleans_the_link_and_names_it_after_the_host(api):
    pid = new_project(api, site_url="shop.example.com/some/page?x=1")
    project = ok(api.get(f"/api/projects/{pid}"))["project"]
    assert project["site_url"] == "https://shop.example.com" and project["name"] == "shop.example.com"
    assert set(project) == {"id", "name", "site_url", "created_at"}


@pytest.mark.parametrize("link", [
    "ftp://x", "localhost", "http://192.168.1.2", "https://user:pw@shop.com",
    "", "   ", "http://10.0.0.5", "http://169.254.169.254/latest", "http://[::1]/", "http://printer.local",
    "http://db.internal", "http://127.0.0.1:8000", "javascript:alert(1)", "https://nodot",
])
def test_bad_project_links_are_400_and_nothing_is_saved(api, link):
    err(api.post("/api/projects", {"name": "x", "site_url": link}), 400)
    assert ok(api.get("/api/projects"))["projects"] == []


def test_project_link_is_required(api):
    err(api.post("/api/projects", {"name": "x"}), 400)
    err(api.post("/api/projects", {"name": "x", "site_url": 42}), 400)


@pytest.mark.xfail(reason="BUG: clean_site_url (index.py:98-108) only blocks dotted-quad IPs and the literal host "
                          "'localhost'; short/hex IPv4 forms and 'localhost.' / '*.localhost' pass and "
                          "requests resolves them to loopback (SSRF)")
@pytest.mark.parametrize("link", ["http://127.1", "http://0x7f.0.0.1", "http://localhost./", "http://admin.localhost"])
def test_loopback_spellings_are_rejected(api, link):
    err(api.post("/api/projects", {"name": "x", "site_url": link}), 400)


def test_projects_newest_first_and_last_run_fills_after_a_run(api, world):
    second = new_project(api, name="Second shop", site_url="https://second.example.com")
    listed = ok(api.get("/api/projects"))["projects"]
    assert [p["id"] for p in listed] == [second, world.pid]
    assert all(p["last_run"] is None for p in listed)
    r1 = run_everything(api, world, {"kind": "full"})
    listed = ok(api.get("/api/projects"))["projects"]
    assert [p["id"] for p in listed] == [second, world.pid]
    assert listed[0]["last_run"] is None
    check_run_info(listed[1]["last_run"])
    assert listed[1]["last_run"] == r1.info and listed[1]["last_run"]["run_number"] == 1
    r2 = run_everything(api, world, {"kind": "full"})
    assert ok(api.get("/api/projects"))["projects"][1]["last_run"]["id"] == r2.id  # the newest run wins


def test_read_one_project(api, world):
    body = ok(api.get(f"/api/projects/{world.pid}"))
    assert set(body) == {"project", "pairs", "runs"}
    assert body["project"]["id"] == world.pid and body["runs"] == []
    assert [p["position"] for p in body["pairs"]] == list(range(1, 9))
    assert [world.names[p["id"]] for p in body["pairs"]] == list(SCENARIO)
    for p in body["pairs"]:
        check_pair(p)
        assert p["has_results"] is False


def test_read_project_after_runs_lists_runs_newest_first_and_marks_has_results(api, world, ran):
    run2 = run_everything(api, world, {"kind": "changed", "pair_ids": [world.ids["search"]]})
    body = ok(api.get(f"/api/projects/{world.pid}"))
    assert [r["run_number"] for r in body["runs"]] == [2, 1]
    for r in body["runs"]:
        check_run_info(r)
    flags = {world.names[p["id"]]: p["has_results"] for p in body["pairs"]}
    assert flags == {**{n: True for n in SCENARIO}, "draft": False}
    assert run2.info["run_number"] == 2


def test_read_unknown_project_is_404(api):
    assert err(api.get(f"/api/projects/{uuid.uuid4()}"), 404) == "We couldn't find this site."


@pytest.mark.xfail(reason="BUG: ids from the URL go straight into a PostgREST filter (index.py:153, 160, 328, 509, "
                          "686); Postgres answers 22P02 for a non-uuid and supa.Db._req (supa.py:139) turns that "
                          "into a 500, but docs/API.md promises 404")
@pytest.mark.parametrize("method,path", [
    ("GET", "/api/projects/not-a-uuid"), ("GET", "/api/runs/not-a-uuid"), ("GET", "/api/runs/not-a-uuid/compare"),
    ("PATCH", "/api/pairs/not-a-uuid"), ("PATCH", "/api/result-checks/not-a-uuid"),
    ("POST", "/api/runs/not-a-uuid/finish"), ("POST", "/api/projects/not-a-uuid/suggestions"),
])
def test_a_malformed_id_in_the_url_is_404(api, method, path):
    err(api.call(method, path, json={"passed": True, "approved": True}), 404)


@pytest.mark.xfail(reason="BUG: compare passes ?with= straight to the database (index.py:654); a non-uuid gives 500")
def test_compare_with_a_malformed_run_id_is_404(api, world, ran):
    err(api.get(f"/api/runs/{ran.id}/compare?with=nonsense"), 404)


# ---------------------------------------------------------------- user B cannot see or touch user A's data

def test_user_b_sees_nothing_of_user_a(env, api, world, ran):
    assert ok(api.get("/api/projects", tok=TOK_B)) == {"projects": []}
    assert err(api.get(f"/api/projects/{world.pid}", tok=TOK_B), 404) == "We couldn't find this site."
    assert err(api.get(f"/api/runs/{ran.id}", tok=TOK_B), 404) == "We couldn't find this run."
    assert err(api.get(f"/api/runs/{ran.id}/compare", tok=TOK_B), 404)
    assert err(api.post(f"/api/runs/{ran.id}/finish", tok=TOK_B), 404)
    assert err(api.post(f"/api/runs/{ran.id}/pairs/{world.ids['search']}", tok=TOK_B), 404)
    assert err(api.post(f"/api/projects/{world.pid}/suggestions", tok=TOK_B), 404)
    assert err(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}, tok=TOK_B), 404)
    body = {"user_does": "x", "good_result": "y", "checks": [chk("status_ok")]}
    assert err(api.post(f"/api/projects/{world.pid}/pairs", body, tok=TOK_B), 404)


def test_user_b_cannot_change_user_a_data(env, api, world, ran):
    before = json.dumps(env.store, sort_keys=True)
    assert err(api.patch(f"/api/pairs/{world.ids['search']}", {"approved": False}, tok=TOK_B), 404)
    manual = ran.rows["collection"][0]["checks"][2]
    assert manual["rule"] == "manual"
    assert err(api.patch(f"/api/result-checks/{manual['id']}", {"passed": True}, tok=TOK_B), 404)
    assert json.dumps(env.store, sort_keys=True) == before
    # and A's manual check is still open
    assert ok(api.get(f"/api/runs/{ran.id}"))["rows"] is not None
    assert ok(api.patch(f"/api/result-checks/{manual['id']}", {"passed": True}))["check"]["passed"] is True


def test_user_b_cannot_compare_into_user_a_runs(api, world, ran):
    mine = new_project(api, tok=TOK_B, site_url="https://b.example.com")
    new_pair(api, mine, "B pair", "/", [chk("status_ok")], tok=TOK_B, approved=True)
    b_run = ok(api.post(f"/api/projects/{mine}/runs", {"kind": "full"}, tok=TOK_B), 201)["run"]
    assert err(api.get(f"/api/runs/{b_run['id']}/compare?with={ran.id}", tok=TOK_B), 404)


def test_user_b_has_their_own_numbering_and_data(api, world, ran):
    b = new_project(api, tok=TOK_B, site_url="https://b.example.com")
    assert [p["id"] for p in ok(api.get("/api/projects", tok=TOK_B))["projects"]] == [b]
    pair = new_pair(api, b, "Mine", "/", [chk("status_ok")], tok=TOK_B, approved=True)
    assert pair["position"] == 1  # A's pairs do not count
    run = ok(api.post(f"/api/projects/{b}/runs", {"kind": "full"}, tok=TOK_B), 201)["run"]
    assert run["run_number"] == 1


# ================================================================ pairs: AI drafts

def test_tidy_returns_a_draft(env, api):
    body = ok(api.post("/api/pairs/tidy", {"rough_text": "  searches solaris  ", "site_url": "shop.example.com"}))
    assert set(body) == {"pair"}
    assert set(body["pair"]) == {"user_does", "good_result", "request_url", "method", "request_body", "checks"}
    assert body["pair"]["user_does"] == "Tidy: searches solaris"
    assert env.groq.called("tidy_pair") == [("tidy_pair", "searches solaris", "https://shop.example.com")]


def test_tidy_kind_change_uses_change_to_pair(env, api):
    body = ok(api.post("/api/pairs/tidy", {"rough_text": "I moved the banner", "site_url": SITE_URL, "kind": "change"}))
    assert body["pair"]["user_does"] == "Changed: I moved the banner"
    assert env.groq.called("change_to_pair") and not env.groq.called("tidy_pair")


@pytest.mark.parametrize("body", [
    {"site_url": SITE_URL}, {"rough_text": "   ", "site_url": SITE_URL}, {"rough_text": "x"},
    {"rough_text": "x", "site_url": "http://localhost"},
])
def test_tidy_bad_input_is_400(env, api, body):
    err(api.post("/api/pairs/tidy", body), 400)
    assert env.groq.calls == []


def test_tidy_when_the_ai_fails_is_502(env, api):
    env.groq.error = groq.GroqError("The AI helper is busy. Please try again.")
    assert err(api.post("/api/pairs/tidy", {"rough_text": "x", "site_url": SITE_URL}), 502) == \
        "The AI helper is busy. Please try again."


def test_suggestions_returns_at_most_five_drafts(env, api, world):
    body = ok(api.post(f"/api/projects/{world.pid}/suggestions"))
    assert set(body) == {"pairs"} and 1 <= len(body["pairs"]) <= 5
    assert all(set(d) == {"user_does", "good_result", "request_url", "method", "request_body", "checks"}
               for d in body["pairs"])
    (call,) = env.groq.called("suggest_pairs")
    assert "Welcome to Example Shop" in call[1] and call[2] == SITE_URL


def test_suggestions_502_when_home_page_unreadable(env, api, world):
    env.site.overrides["/"] = (500, "boom")
    err(api.post(f"/api/projects/{world.pid}/suggestions"), 502)
    env.site.overrides["/"] = (403, "Forbidden")  # blocked home page counts as unreadable too
    err(api.post(f"/api/projects/{world.pid}/suggestions"), 502)
    assert env.groq.called("suggest_pairs") == []


def test_suggestions_ai_failure_is_502_and_unknown_project_404(env, api, world):
    env.groq.error = groq.GroqError("nope")
    err(api.post(f"/api/projects/{world.pid}/suggestions"), 502)
    err(api.post(f"/api/projects/{uuid.uuid4()}/suggestions"), 404)


# ================================================================ pairs: create + patch

def test_create_pair_201_shape_and_defaults(api):
    pid = new_project(api)
    body = {"user_does": " Searches Solaris ", "good_result": "Solaris shows up",
            "request_url": "/search?q=Solaris", "checks": [chk("status_ok"), chk("text_has", "Solaris"),
                                                           chk("ai_judge", "Is it there?"), chk("manual", "Look")]}
    resp = api.post(f"/api/projects/{pid}/pairs", body)
    assert resp.status_code == 201
    data = resp.json()
    assert set(data) == {"id", "pair"} and data["id"] == data["pair"]["id"]
    pair = data["pair"]
    check_pair(pair)
    assert pair["project_id"] == pid and pair["position"] == 1 and pair["user_does"] == "Searches Solaris"
    assert pair["method"] == "GET" and pair["source"] == "builder" and pair["approved"] is False
    assert pair["is_priority"] is False and pair["has_results"] is False and pair["request_body"] is None
    assert [(c["decided_by"], c["rule"], c["expected"]) for c in pair["checks"]] == [
        ("code", "status_ok", None), ("code", "text_has", "Solaris"), ("ai", "ai_judge", "Is it there?"),
        ("human", "manual", "Look")]


def test_create_pair_defaults_url_and_accepts_flags_and_post_body(api):
    pid = new_project(api)
    pair = new_pair(api, pid, "Adds to cart", "/cart/add.js", [chk("count_equals", "item_count=1")],
                    method="post", request_body={"id": 123, "quantity": 1}, source="suggested", approved=True,
                    is_priority=True)
    assert pair["method"] == "POST" and pair["request_body"] == {"id": 123, "quantity": 1}
    assert pair["source"] == "suggested" and pair["approved"] is True and pair["is_priority"] is True
    body = {"user_does": "a", "good_result": "b", "checks": [chk("status_ok")]}
    plain = ok(api.post(f"/api/projects/{pid}/pairs", body), 201)["pair"]
    assert plain["request_url"] == "/" and plain["method"] == "GET" and plain["position"] == 2


def test_create_pair_ignores_a_wrong_decided_by(api):
    pid = new_project(api)
    pair = new_pair(api, pid, "x", "/", [{"decided_by": "human", "rule": "status_ok", "expected": None}])
    assert pair["checks"][0]["decided_by"] == "code"


def test_pair_positions_increment(api):
    pid = new_project(api)
    assert [new_pair(api, pid, f"p{i}", "/", [chk("status_ok")])["position"] for i in range(3)] == [1, 2, 3]
    other = new_project(api, site_url="https://other.example.com")
    assert new_pair(api, other, "first", "/", [chk("status_ok")])["position"] == 1


GOOD = {"user_does": "a", "good_result": "b", "request_url": "/", "checks": [chk("status_ok")]}


@pytest.mark.parametrize("change,message", [
    ({"user_does": None}, "Please fill in what the user does."),
    ({"user_does": "   "}, "Please fill in what the user does."),
    ({"good_result": ""}, "Please fill in what a good result looks like."),
    ({"checks": []}, "Please add at least one check."),
    ({"checks": None}, "Please add at least one check."),
    ({"checks": "status_ok"}, "The checks are not valid."),
    ({"checks": [{"rule": "magic"}]}, "One of the checks is not valid."),
    ({"checks": ["status_ok"]}, "One of the checks is not valid."),
    ({"checks": [chk("text_has")]}, "One of the checks needs something to look for."),
    ({"checks": [chk("manual", " ")]}, "One of the checks needs something to look for."),
    ({"checks": [chk("count_equals")]}, "One of the checks needs something to look for."),
    ({"checks": [chk("status_ok")] * 11}, "Please keep it to 10 checks per pair."),
    ({"request_url": "http://evil.com"}, "The page to open must start with / (for example /search?q=Solaris)."),
    ({"request_url": "//evil.com/x"}, "The page to open must start with / (for example /search?q=Solaris)."),
    ({"request_url": 7}, "The page to open must start with / (for example /search?q=Solaris)."),
    ({"method": "DELETE"}, "Method must be GET or POST."),
    ({"request_body": "text"}, "The data to send must be JSON."),
])
def test_create_pair_bad_input_is_400_and_saves_nothing(env, api, change, message):
    pid = new_project(api)
    assert err(api.post(f"/api/projects/{pid}/pairs", {**GOOD, **change}), 400) == message
    assert ok(api.get(f"/api/projects/{pid}"))["pairs"] == []
    assert env.store.count("checks") == 0  # no orphan checks either


def test_create_pair_minimal_checks_are_allowed(api):
    pid = new_project(api)
    pair = new_pair(api, pid, "x", "/", [chk("status_ok"), chk("min_results")])
    assert [c["rule"] for c in pair["checks"]] == ["status_ok", "min_results"]


def test_create_pair_in_unknown_project_is_404(api):
    assert err(api.post(f"/api/projects/{uuid.uuid4()}/pairs", GOOD), 404) == "We couldn't find this site."


@pytest.mark.xfail(reason="BUG: clean_checks (index.py:119) does `c.get('rule') not in RULE_DECIDER`; an unhashable "
                          "rule such as ['status_ok'] raises TypeError -> 500 instead of 400")
def test_create_pair_with_a_list_as_rule_is_400_not_500(api):
    pid = new_project(api)
    err(api.post(f"/api/projects/{pid}/pairs", {**GOOD, "checks": [{"rule": ["status_ok"]}]}), 400)


def test_patch_pair_flags_and_text(api):
    pid = new_project(api)
    pair = new_pair(api, pid, "Old", "/", [chk("status_ok")])
    url = f"/api/pairs/{pair['id']}"
    body = ok(api.patch(url, {"approved": True}))
    assert set(body) == {"pair"} and body["pair"]["approved"] is True
    check_pair(body["pair"])
    assert ok(api.patch(url, {"is_priority": True}))["pair"]["is_priority"] is True
    got = ok(api.patch(url, {"user_does": " New does ", "good_result": "New good", "request_url": "/search?q=a",
                             "method": "POST", "request_body": {"id": 1}}))["pair"]
    assert (got["user_does"], got["good_result"], got["request_url"], got["method"], got["request_body"]) == \
        ("New does", "New good", "/search?q=a", "POST", {"id": 1})
    assert got["approved"] is True and got["is_priority"] is True  # untouched fields stay
    assert ok(api.patch(url, {"approved": False}))["pair"]["approved"] is False
    assert ok(api.patch(url, {}))["pair"]["id"] == pair["id"]  # nothing to change is fine


@pytest.mark.parametrize("body", [
    {"approved": "yes"}, {"is_priority": 1}, {"user_does": ""}, {"good_result": "  "},
    {"request_url": "http://evil.com"}, {"method": "PUT"}, {"request_body": "x"}, {"checks": []},
    {"checks": [{"rule": "nope"}]},
])
def test_patch_pair_bad_input_is_400_and_changes_nothing(api, body):
    pid = new_project(api)
    pair = new_pair(api, pid, "Keep", "/", [chk("status_ok")])
    err(api.patch(f"/api/pairs/{pair['id']}", body), 400)
    after = ok(api.get(f"/api/projects/{pid}"))["pairs"][0]
    assert {k: after[k] for k in pair if k != "has_results"} == {k: v for k, v in pair.items() if k != "has_results"}


def test_patch_unknown_pair_is_404(api):
    assert err(api.patch(f"/api/pairs/{uuid.uuid4()}", {"approved": True}), 404) == "We couldn't find that pair."


def test_patch_checks_before_a_run_replaces_them(api):
    pid = new_project(api)
    pair = new_pair(api, pid, "x", "/", [chk("status_ok"), chk("text_has", "Old")])
    got = ok(api.patch(f"/api/pairs/{pair['id']}", {"checks": [chk("min_results", "3"), chk("manual", "Look")]}))["pair"]
    assert [(c["rule"], c["expected"]) for c in got["checks"]] == [("min_results", "3"), ("manual", "Look")]
    assert all(c["id"] not in {o["id"] for o in pair["checks"]} for c in got["checks"])
    assert [c["rule"] for c in ok(api.get(f"/api/projects/{pid}"))["pairs"][0]["checks"]] == ["min_results", "manual"]


def test_patch_checks_after_a_run_is_409_but_other_edits_are_fine(env, api, world, ran):
    url = f"/api/pairs/{world.ids['search']}"
    before = env.store.count("checks")
    msg = err(api.patch(url, {"checks": [chk("status_ok")]}), 409)
    assert msg.startswith("Checks are locked after a run")
    assert env.store.count("checks") == before
    # the results still point at the original checks
    assert env.store.count("result_checks") == sum(len(r["checks"]) for rows in ran.rows.values() for r in rows)
    got = ok(api.patch(url, {"approved": False, "is_priority": True}))["pair"]
    assert got["approved"] is False and got["is_priority"] is True and got["has_results"] is True
    assert [c["rule"] for c in got["checks"]] == ["status_ok", "min_results", "text_has", "ai_judge"]


# ================================================================ starting a run (door 8)

def test_full_run_with_no_approved_pairs_is_400(api):
    pid = new_project(api)
    assert err(api.post(f"/api/projects/{pid}/runs", {"kind": "full"}), 400) == "Approve at least one pair before running."
    new_pair(api, pid, "Not approved", "/", [chk("status_ok")])  # still unapproved
    err(api.post(f"/api/projects/{pid}/runs", {"kind": "full"}), 400)
    assert ok(api.get(f"/api/projects/{pid}"))["runs"] == []  # no run row was left behind


@pytest.mark.parametrize("body", [{}, {"kind": "half"}, {"kind": None}, {"kind": ["full"]}])
def test_run_needs_a_valid_kind(api, world, body):
    err(api.post(f"/api/projects/{world.pid}/runs", body), 400)


def test_approve_pairs_one_priority_then_full_run(api):
    pid = new_project(api)
    a = new_pair(api, pid, "A", "/", [chk("status_ok")])
    b = new_pair(api, pid, "B", "/", [chk("status_ok")])
    c = new_pair(api, pid, "C", "/", [chk("status_ok")])
    for p in (a, b, c):
        ok(api.patch(f"/api/pairs/{p['id']}", {"approved": True}))
    ok(api.patch(f"/api/pairs/{c['id']}", {"is_priority": True}))
    resp = api.post(f"/api/projects/{pid}/runs", {"kind": "full"})
    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {"run", "pair_ids"}
    check_run_info(body["run"])
    assert body["run"]["run_number"] == 1 and body["run"]["kind"] == "full"
    assert (body["run"]["passed"], body["run"]["total"]) == (0, 0)
    assert body["pair_ids"] == [c["id"], a["id"], b["id"]]  # priority first, then position


def test_full_run_leaves_out_unapproved_pairs(api, world):
    started = ok(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}), 201)
    names = [world.names[i] for i in started["pair_ids"]]
    assert names == ["cart", "search", "collection", "blocked", "dead", "look", "slow"]


def test_run_numbers_count_up_per_project(api, world):
    one = ok(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}), 201)["run"]
    two = ok(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}), 201)["run"]
    assert (one["run_number"], two["run_number"]) == (1, 2)
    other = new_project(api, site_url="https://other.example.com")
    new_pair(api, other, "x", "/", [chk("status_ok")], approved=True)
    assert ok(api.post(f"/api/projects/{other}/runs", {"kind": "full"}), 201)["run"]["run_number"] == 1


def test_run_number_race_is_retried(env, api, world):
    """Another request takes run number 1 between our look and our insert: we must end up as number 2."""
    def rival(store, rows):
        FakeDb(TOK_A, store).insert("runs", {"project_id": world.pid, "run_number": 1, "kind": "full"})

    env.store.before_insert["runs"] = rival
    run = ok(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}), 201)["run"]
    assert run["run_number"] == 2
    assert [r["run_number"] for r in ok(api.get(f"/api/projects/{world.pid}"))["runs"]] == [2, 1]


def test_changed_run_validation(api, world):
    url = f"/api/projects/{world.pid}/runs"
    err(api.post(url, {"kind": "changed"}), 400)
    err(api.post(url, {"kind": "changed", "pair_ids": []}), 400)
    err(api.post(url, {"kind": "changed", "pair_ids": "cart"}), 400)
    err(api.post(url, {"kind": "changed", "pair_ids": [world.ids["draft"]]}), 400)  # not approved
    err(api.post(url, {"kind": "changed", "pair_ids": [str(uuid.uuid4())]}), 400)
    err(api.post(url, {"kind": "changed", "pair_ids": [world.ids["cart"]], "other_pair_id": world.ids["draft"]}), 400)
    other = new_project(api, site_url="https://other.example.com")
    foreign = new_pair(api, other, "x", "/", [chk("status_ok")], approved=True)
    err(api.post(url, {"kind": "changed", "pair_ids": [foreign["id"]]}), 400)  # a pair of another site
    assert ok(api.get(f"/api/projects/{world.pid}"))["runs"] == []


def test_changed_run_picks_pairs_in_priority_order_without_duplicates(api, world):
    body = {"kind": "changed", "pair_ids": [world.ids["search"], world.ids["cart"], world.ids["search"]]}
    started = ok(api.post(f"/api/projects/{world.pid}/runs", body), 201)
    assert started["run"]["kind"] == "changed"
    assert started["pair_ids"] == [world.ids["cart"], world.ids["search"]]


@pytest.mark.xfail(reason="BUG: create_run (index.py:376) does `i not in approved` with the dict `approved`; an "
                          "unhashable entry in pair_ids (e.g. [[1]]) raises TypeError -> 500 instead of 400")
def test_changed_run_with_junk_pair_ids_is_400_not_500(api, world):
    err(api.post(f"/api/projects/{world.pid}/runs", {"kind": "changed", "pair_ids": [["x"]]}), 400)


# ================================================================ testing one pair (door 9)

def test_door_9_returns_phone_and_laptop_rows_for_a_passing_pair(env, api, world):
    run_id = ok(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}), 201)["run"]["id"]
    resp = api.post(f"/api/runs/{run_id}/pairs/{world.ids['search']}")
    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {"rows"} and [r["device"] for r in body["rows"]] == ["phone", "laptop"]
    for row in body["rows"]:
        check_row(row)
        assert row["run_id"] == run_id and row["pair_id"] == world.ids["search"]
        assert row["position"] == 1 and row["user_does"] == "Search" and row["is_priority"] is False
        assert row["good_result"] == "Good: Search"
        assert row["status_code"] == 200 and row["outcome"] == "pass" and row["why"] == ""
        assert "Solaris" in row["what_site_said"] and len(row["what_site_said"]) <= 500
        assert [(c["decided_by"], c["rule"], c["passed"]) for c in row["checks"]] == [
            ("code", "status_ok", True), ("code", "min_results", True), ("code", "text_has", True),
            ("ai", "ai_judge", True)]
        assert row["checks"][1]["why"] == "Found 2 products (needed at least 2)."
        assert row["checks"][3]["why"] == "AI: looks right."
    assert {c[0] for c in env.site.calls_to("/search?q=Solaris")} == {"phone", "laptop"}


def test_door_9_twice_returns_the_same_saved_rows(env, api, world):
    run_id = ok(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}), 201)["run"]["id"]
    url = f"/api/runs/{run_id}/pairs/{world.ids['collection']}"
    first = ok(api.post(url), 201)["rows"]
    fetches = len(env.site.calls)
    second = ok(api.post(url), 201)["rows"]
    assert second == first and [r["result_id"] for r in second] == [r["result_id"] for r in first]
    assert len(env.site.calls) == fetches  # the site was not asked again
    assert env.store.count("results", run_id=run_id) == 2
    assert env.store.count("result_checks") == 6  # 3 checks x 2 devices, no duplicates


def test_door_9_survives_a_parallel_call_saving_a_device_first(env, api, world):
    run_id = ok(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}), 201)["run"]["id"]
    pair_id = world.ids["look"]
    check_id = env.store["checks"][[c["golden_pair_id"] for c in env.store["checks"]].index(pair_id)]["id"]

    def rival(store, rows):
        res = FakeDb(TOK_A, store).insert("results", {"run_id": run_id, "golden_pair_id": pair_id, "device": "phone",
                                                       "outcome": "cant_test", "what_site_said": "from the other call"})[0]
        FakeDb(TOK_A, store).insert("result_checks", {"result_id": res["id"], "check_id": check_id,
                                                        "passed": None, "why": "You look: x"})

    env.store.before_insert["results"] = rival
    rows = ok(api.post(f"/api/runs/{run_id}/pairs/{pair_id}"), 201)["rows"]
    assert [r["device"] for r in rows] == ["phone", "laptop"]
    assert rows[0]["what_site_said"] == "from the other call"  # kept the saved one, no duplicate, no crash
    assert env.store.count("results", run_id=run_id) == 2


def test_door_9_blocked_page_is_cant_test(env, api, world, ran):
    for row in ran.rows["blocked"]:
        check_row(row)
        assert row["outcome"] == "cant_test" and row["status_code"] == 403
        assert row["why"] == BLOCKED_WHY == "The site blocked us, so we can't test this."
        assert [c["passed"] for c in row["checks"]] == [None, None]
        assert all(c["why"] == BLOCKED_WHY for c in row["checks"])
        assert row["what_site_said"] == "The site blocked us (status 403)."
    assert all(c[1] != world.ids["blocked"] for c in env.groq.called("judge"))  # nothing to ask the AI about


def test_door_9_404_page_fails_with_the_status_check_carrying_the_reason(env, api, world, ran):
    for row in ran.rows["dead"]:
        check_row(row)
        assert row["outcome"] == "fail" and row["status_code"] == 404
        status, has, absent = row["checks"]
        assert (status["rule"], status["passed"]) == ("status_ok", False)
        assert "404" in status["why"] and status["why"] != NOT_CHECKED
        for other in (has, absent):
            assert other["passed"] is False and other["why"] == NOT_CHECKED
        assert row["why"] == status["why"]
        assert "Page not found" in row["what_site_said"]


def test_door_9_timeout_is_a_fail_with_the_timeout_reason(env, api, world, ran):
    for row in ran.rows["slow"]:
        check_row(row)
        assert row["outcome"] == "fail" and row["status_code"] is None
        assert site.TIMEOUT_MESSAGE in row["checks"][0]["why"] and row["checks"][1]["why"] == NOT_CHECKED
        assert row["what_site_said"] == site.TIMEOUT_MESSAGE


@pytest.mark.xfail(reason="BUG: _row_why (index.py:461-471) returns the FIRST check with passed False; when "
                          "text_has/min_results come before status_ok on a dead page, the row's one-line why "
                          "becomes 'Not checked, because the page didn't load.' instead of the 404 reason")
def test_row_why_is_the_real_reason_even_when_status_check_is_not_first(api):
    pid = new_project(api)
    pair = new_pair(api, pid, "Dead page", "/broken", [chk("text_has", "Solaris"), chk("status_ok")], approved=True)
    run_id = ok(api.post(f"/api/projects/{pid}/runs", {"kind": "full"}), 201)["run"]["id"]
    for row in ok(api.post(f"/api/runs/{run_id}/pairs/{pair['id']}"), 201)["rows"]:
        assert row["outcome"] == "fail" and "404" in row["why"]


def test_door_9_cart_post_is_checked_against_the_cart(env, api, world, ran):
    phone, laptop = ran.rows["cart"]
    assert (phone["outcome"], laptop["outcome"]) == ("pass", "fail")
    assert phone["is_priority"] is True and phone["position"] == 4
    assert phone["what_site_said"].startswith("Cart has 1 item: 1 × Solaris – Black")
    assert laptop["what_site_said"].startswith("Cart has 5 items")
    assert laptop["checks"][0]["passed"] is True
    count = laptop["checks"][1]
    assert (count["rule"], count["expected"], count["passed"]) == ("count_equals", "item_count=1", False)
    assert "item_count = 5" in count["why"] and laptop["why"] == count["why"]
    sent = env.site.calls_to("/cart/add.js")
    assert sorted(c[0] for c in sent) == ["laptop", "phone"]
    assert all(c[1:] == ("POST", "/cart/add.js", {"items": [{"handle": "solaris", "quantity": 1}]}) for c in sent)


def test_door_9_manual_check_waits_for_a_human(api, world, ran):
    for row in ran.rows["collection"]:
        assert row["outcome"] == "pass" and row["why"] == ""  # the code checks passed, the human check is open
        status, text, manual = row["checks"]
        assert (status["passed"], text["passed"]) == (True, True)
        assert (manual["decided_by"], manual["rule"], manual["passed"]) == ("human", "manual", None)
        assert manual["why"] == "You look: Do the product photos look right?"


def test_door_9_pair_with_only_manual_checks_is_cant_test(api, world, ran):
    for row in ran.rows["look"]:
        check_row(row)
        assert row["outcome"] == "cant_test" and row["status_code"] == 200 and row["why"] == LOOK_WHY
        assert [c["passed"] for c in row["checks"]] == [None]
        assert row["checks"][0]["why"] == "You look: Does the home page look friendly?"


def test_door_9_errors(env, api, world):
    run_id = ok(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}), 201)["run"]["id"]
    assert err(api.post(f"/api/runs/{run_id}/pairs/{world.ids['draft']}"), 400) == "This pair isn't approved yet."
    assert err(api.post(f"/api/runs/{run_id}/pairs/{uuid.uuid4()}"), 404)
    assert err(api.post(f"/api/runs/{uuid.uuid4()}/pairs/{world.ids['search']}"), 404) == "We couldn't find this run."
    other = new_project(api, site_url="https://other.example.com")
    foreign = new_pair(api, other, "x", "/", [chk("status_ok")], approved=True)
    assert err(api.post(f"/api/runs/{run_id}/pairs/{foreign['id']}"), 404)
    assert env.store.count("results") == 0


# ---------------------------------------------------------------- the AI cannot decide

def make_ai_pair(api, extra_checks=()):
    pid = new_project(api)
    pair = new_pair(api, pid, "AI only", "/search?q=Solaris", [*extra_checks, chk("ai_judge", "Is Solaris shown?")],
                    approved=True)
    run_id = ok(api.post(f"/api/projects/{pid}/runs", {"kind": "full"}), 201)["run"]["id"]
    return pid, pair, run_id


@pytest.mark.parametrize("mode", ["unsure", "empty"])
def test_ai_unsure_alone_is_cant_test_and_a_human_can_answer(env, api, mode):
    env.groq.mode = mode
    pid, pair, run_id = make_ai_pair(api)
    rows = ok(api.post(f"/api/runs/{run_id}/pairs/{pair['id']}"), 201)["rows"]
    for row in rows:
        check_row(row)
        assert row["outcome"] == "cant_test" and row["why"] == UNSURE_ROW_WHY
        (ai,) = row["checks"]
        assert (ai["decided_by"], ai["passed"], ai["why"]) == ("ai", None, groq.AI_UNSURE)
    answered = ok(api.patch(f"/api/result-checks/{rows[0]['checks'][0]['id']}", {"passed": True}))["check"]
    assert answered["passed"] is True and answered["decided_by"] == "ai"


def test_ai_unsure_next_to_a_passing_code_check_is_a_pass(env, api):
    env.groq.mode = "unsure"
    pid, pair, run_id = make_ai_pair(api, [chk("status_ok")])
    for row in ok(api.post(f"/api/runs/{run_id}/pairs/{pair['id']}"), 201)["rows"]:
        assert row["outcome"] == "pass" and row["why"] == ""
        assert [c["passed"] for c in row["checks"]] == [True, None]
        assert row["checks"][1]["why"] == groq.AI_UNSURE


def test_real_judge_returns_ai_unsure_when_groq_is_down(env, api, monkeypatch):
    monkeypatch.setattr(groq, "judge", REAL_JUDGE)

    def down(*a, **k):
        raise groq.GroqError("down")

    monkeypatch.setattr(groq, "chat_json", down)
    pid, pair, run_id = make_ai_pair(api, [chk("text_has", "Solaris")])
    for row in ok(api.post(f"/api/runs/{run_id}/pairs/{pair['id']}"), 201)["rows"]:
        assert row["outcome"] == "pass"
        assert row["checks"][1]["passed"] is None and row["checks"][1]["why"] == groq.AI_UNSURE


def test_ai_check_that_says_no_fails_the_row(env, api):
    env.site.overrides["/search?q=Solaris"] = (200, html("Search", "<p>Nothing here</p>"))
    pid, pair, run_id = make_ai_pair(api, [chk("status_ok")])
    for row in ok(api.post(f"/api/runs/{run_id}/pairs/{pair['id']}"), 201)["rows"]:
        assert row["outcome"] == "fail" and row["why"] == "AI: Solaris is not on the page."


# ================================================================ finishing + reading a run (doors 10, 11)

def test_finish_counts_and_points(env, api, world, ran):
    done = ran.done
    assert set(done) == {"run", "points", "changed"}
    check_run_info(done["run"])
    assert done["run"]["id"] == ran.id and (done["run"]["passed"], done["run"]["total"]) == (5, 14)
    assert done["changed"] == []
    points = done["points"]
    assert 1 <= len(points) <= 3 and len(points) == 3  # five failed results, only the 3 worst are kept
    assert [p["rank"] for p in points] == [1, 2, 3]
    for p in points:
        check_point(p)
        assert p["explanation"] == f"explanation for {p['result_id']}"
    assert (points[0]["pair_id"], points[0]["device"]) == (world.ids["cart"], "laptop")  # the priority fail is #1
    assert points[0]["position"] == 4 and points[0]["user_does"] == "Cart"
    assert points[0]["what_site_said"].startswith("Cart has 5 items")
    # different pairs come before a second device of the same pair
    assert [(world.names[p["pair_id"]], p["device"]) for p in points] == \
        [("cart", "laptop"), ("dead", "phone"), ("slow", "phone")]
    assert env.store.count("diagnosis_points") == 3


def test_finish_sends_the_failed_checks_to_diagnose(env, api, world, ran):
    (call,) = env.groq.called("diagnose")
    items = call[1]
    assert len(items) == 3 and call[2] == 40
    first = items[0]
    assert set(first) == {"result_id", "user_does", "good_result", "device", "status_code", "what_site_said",
                          "failed_checks"}
    assert first["failed_checks"] == [{"rule": "count_equals", "expected": "item_count=1",
                                       "why": "AI: The cart shows item_count = 5 (expected 1)."}]


def test_finish_twice_gives_the_same_points_without_duplicates(env, api, world, ran):
    again = ok(api.post(f"/api/runs/{ran.id}/finish"))
    assert again["points"] == ran.done["points"] and again["run"] == ran.done["run"]
    assert env.store.count("diagnosis_points") == 3 and len(env.groq.called("diagnose")) == 1


def test_finish_with_no_fails_has_no_points(env, api):
    pid = new_project(api)
    for url in ("/search?q=Solaris", "/collections/cabinet-lights"):
        new_pair(api, pid, url, url, [chk("status_ok")], approved=True)
    w = SimpleNamespace(pid=pid, names={p["id"]: p["user_does"] for p in ok(api.get(f"/api/projects/{pid}"))["pairs"]})
    r = run_everything(api, w, {"kind": "full"})
    assert r.done["points"] == [] and r.info["passed"] == 4 and r.info["total"] == 4
    assert env.groq.called("diagnose") == [] and env.store.count("diagnosis_points") == 0
    assert ok(api.post(f"/api/runs/{r.id}/finish"))["points"] == []


def test_finish_with_one_failure_has_one_point(env, api):
    pid = new_project(api)
    pair = new_pair(api, pid, "Dead", "/broken", [chk("status_ok")], approved=True)
    run_id = ok(api.post(f"/api/projects/{pid}/runs", {"kind": "full"}), 201)["run"]["id"]
    ok(api.post(f"/api/runs/{run_id}/pairs/{pair['id']}"), 201)
    done = ok(api.post(f"/api/runs/{run_id}/finish"))
    assert [(p["rank"], p["device"]) for p in done["points"]] == [(1, "phone"), (2, "laptop")]
    assert (done["run"]["passed"], done["run"]["total"]) == (0, 2)


def test_finish_race_keeps_the_points_saved_by_the_other_call(env, api, world):
    run_id = ok(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}), 201)["run"]["id"]
    for pair_id in (world.ids["cart"], world.ids["dead"]):
        ok(api.post(f"/api/runs/{run_id}/pairs/{pair_id}"), 201)
    result = env.store["results"][0]

    def rival(store, rows):
        FakeDb(TOK_A, store).insert("diagnosis_points", [{"run_id": run_id, "result_id": result["id"], "rank": 1,
                                                         "explanation": "saved by the other finish"}])

    env.store.before_insert["diagnosis_points"] = rival
    done = ok(api.post(f"/api/runs/{run_id}/finish"))
    assert [p["explanation"] for p in done["points"]] == ["saved by the other finish"]


def test_finish_unknown_run_is_404(api):
    err(api.post(f"/api/runs/{uuid.uuid4()}/finish"), 404)


def test_diagnose_missing_text_falls_back_to_the_row_reason(env, api, world, monkeypatch):
    monkeypatch.setattr(groq, "diagnose", lambda items, timeout=None: {})
    r = run_everything(api, world, {"kind": "changed", "pair_ids": [world.ids["cart"]]})
    (point,) = r.done["points"]
    assert point["explanation"] == "AI: The cart shows item_count = 5 (expected 1)."


def test_read_run_shape_and_order(api, world, ran):
    body = ok(api.get(f"/api/runs/{ran.id}"))
    assert set(body) == {"run", "project", "rows", "points", "changed", "earlier_runs"}
    check_run_info(body["run"])
    assert body["run"] == ran.info
    assert body["project"] == {"id": world.pid, "name": "Example Shop", "site_url": SITE_URL}
    assert body["points"] == ran.done["points"] and body["changed"] == [] and body["earlier_runs"] == []
    assert len(body["rows"]) == 14
    for row in body["rows"]:
        check_row(row)
    # priority first, then pairs with any fail, then the rest, by position; phone before laptop
    assert pair_order(world, body["rows"]) == ["cart", "dead", "slow", "search", "collection", "blocked", "look"]
    assert [r["device"] for r in body["rows"]] == ["phone", "laptop"] * 7
    # the rows read back are the rows door 9 returned
    by_pair = {}
    for row in body["rows"]:
        by_pair.setdefault(world.names[row["pair_id"]], []).append(row)
    assert by_pair == ran.rows


def test_read_run_unknown_is_404(api):
    assert err(api.get(f"/api/runs/{uuid.uuid4()}"), 404) == "We couldn't find this run."


def test_read_run_before_finishing_has_no_points(api, world):
    run_id = ok(api.post(f"/api/projects/{world.pid}/runs", {"kind": "full"}), 201)["run"]["id"]
    ok(api.post(f"/api/runs/{run_id}/pairs/{world.ids['dead']}"), 201)
    body = ok(api.get(f"/api/runs/{run_id}"))
    assert body["points"] == [] and len(body["rows"]) == 2 and (body["run"]["passed"], body["run"]["total"]) == (0, 0)


# ================================================================ a human answers a check (door 13)

def test_answer_manual_check_true_then_409(api, world, ran):
    manual = ran.rows["collection"][0]["checks"][2]
    resp = api.patch(f"/api/result-checks/{manual['id']}", {"passed": True})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"check"} and set(body["check"]) == CHECK_RESULT
    assert body["check"] == {"id": manual["id"], "check_id": manual["check_id"], "decided_by": "human",
                             "rule": "manual", "expected": "Do the product photos look right?", "passed": True,
                             "why": "You said it looks right."}
    assert err(api.patch(f"/api/result-checks/{manual['id']}", {"passed": False}), 409) == \
        "This check already has an answer."
    seen = ok(api.get(f"/api/runs/{ran.id}"))["rows"]
    row = next(r for r in seen if r["result_id"] == ran.rows["collection"][0]["result_id"])
    assert row["checks"][2]["passed"] is True and row["checks"][2]["why"] == "You said it looks right."


def test_answer_manual_check_false(api, world, ran):
    manual = ran.rows["collection"][1]["checks"][2]
    check = ok(api.patch(f"/api/result-checks/{manual['id']}", {"passed": False}))["check"]
    assert check["passed"] is False and check["why"] == "You said it looks wrong."


def test_answering_a_check_that_was_already_decided_is_409(api, world, ran):
    decided = ran.rows["search"][0]["checks"][0]  # status_ok, passed by code
    err(api.patch(f"/api/result-checks/{decided['id']}", {"passed": False}), 409)
    row = ok(api.get(f"/api/runs/{ran.id}"))["rows"]
    assert all(c["passed"] is True for r in row if r["pair_id"] == world.ids["search"] for c in r["checks"])


@pytest.mark.parametrize("body", [{}, {"passed": "yes"}, {"passed": None}, {"passed": 1}])
def test_answer_needs_a_boolean(api, world, ran, body):
    manual = ran.rows["collection"][0]["checks"][2]
    err(api.patch(f"/api/result-checks/{manual['id']}", body), 400)
    assert ok(api.patch(f"/api/result-checks/{manual['id']}", {"passed": True}))["check"]["passed"] is True


def test_answer_unknown_check_is_404(api):
    assert err(api.patch(f"/api/result-checks/{uuid.uuid4()}", {"passed": True}), 404) == "We couldn't find that check."


# ================================================================ re-running what changed + comparing

def test_changed_rerun_run_two_and_changed_list(env, api, world, ran, rerun):
    assert rerun.started["run"]["run_number"] == 2 and rerun.started["run"]["kind"] == "changed"
    assert rerun.started["pair_ids"] == [world.ids["cart"], world.ids["banner"]]
    assert sorted(rerun.rows) == ["banner", "cart"]  # only the chosen pairs ran
    done = rerun.done
    assert (done["run"]["passed"], done["run"]["total"]) == (4, 4) and done["points"] == []
    assert len(done["changed"]) == 2
    for c in done["changed"]:
        assert set(c) == CHANGED
    cart, banner = done["changed"]
    assert cart == {"pair_id": world.ids["cart"], "position": 4, "user_does": "Cart", "note": "Ticked as changed",
                    "phone": "pass", "laptop": "pass", "good_now": "yes"}
    assert banner == {"pair_id": world.ids["banner"], "position": 9, "user_does": "Reads the banner",
                      "note": "I changed the shipping banner", "phone": "pass", "laptop": "pass", "good_now": "yes"}
    assert ok(api.get(f"/api/runs/{rerun.id}"))["changed"] == done["changed"]


def test_changed_good_now_is_no_while_still_broken(env, api, world, ran):
    r = run_everything(api, world, {"kind": "changed", "pair_ids": [world.ids["cart"]]})  # shop still broken
    (c,) = r.done["changed"]
    assert (c["phone"], c["laptop"], c["good_now"]) == ("pass", "fail", "no")
    assert c["note"] == "Ticked as changed"


def test_changed_note_without_a_pair_is_kept_but_not_listed(env, api, world, ran):
    r = run_everything(api, world, {"kind": "changed", "pair_ids": [world.ids["search"]],
                                    "other_changes": "Changed the footer"})
    assert [c["pair_id"] for c in r.done["changed"]] == [world.ids["search"]]
    assert [(c["golden_pair_id"], c["note"]) for c in env.store["changes"] if c["run_id"] == r.id] == \
        [(world.ids["search"], "Ticked as changed"), (None, "Changed the footer")]


def test_full_run_has_no_changed_entries_and_stores_no_changes(env, api, ran):
    assert env.store["changes"] == [] and ran.done["changed"] == []


def test_rerun_leaves_run_one_untouched(env, api, world, ran):
    def stored():
        results = [r for r in env.store["results"] if r["run_id"] == ran.id]
        ids = {r["id"] for r in results}
        return json.dumps([results, [c for c in env.store["result_checks"] if c["result_id"] in ids],
                           [p for p in env.store["diagnosis_points"] if p["run_id"] == ran.id]], sort_keys=True)

    snap_body, snap_store = ok(api.get(f"/api/runs/{ran.id}")), stored()
    env.site.version = "fixed"
    run_everything(api, world, {"kind": "full"})  # even a second FULL run on the fixed shop
    assert ok(api.get(f"/api/runs/{ran.id}")) == snap_body
    assert stored() == snap_store


def test_rerun_does_not_change_run_one_even_through_the_api_rules(env, api, world, ran):
    """The database refuses to overwrite a result: update and delete are silent no-ops."""
    db = FakeDb(TOK_A, env.store)
    victim = env.store["results"][0]
    before = dict(victim)
    assert db.update("results", {"outcome": "pass"}, id=f"eq.{victim['id']}") == []
    assert db.delete("results", id=f"eq.{victim['id']}") == []
    assert env.store["results"][0] == before


def test_read_run_two_has_earlier_runs(api, world, ran, rerun):
    body = ok(api.get(f"/api/runs/{rerun.id}"))
    assert [r["id"] for r in body["earlier_runs"]] == [ran.id]
    check_run_info(body["earlier_runs"][0])
    assert body["earlier_runs"][0] == ran.info
    assert pair_order(world, body["rows"]) == ["cart", "banner"]


def test_compare_run_two_with_run_one(api, world, ran, rerun):
    body = ok(api.get(f"/api/runs/{rerun.id}/compare?with={ran.id}"))
    assert set(body) == {"run", "old_run", "rows"}
    assert body["run"] == rerun.info and body["old_run"] == ran.info
    expect = [("cart", "phone", "pass", "pass", "same"), ("cart", "laptop", "fail", "pass", "FIXED"),
              ("banner", "phone", None, "pass", "same"), ("banner", "laptop", None, "pass", "same")]
    assert [(world.names[r["pair_id"]], r["device"], r["old_outcome"], r["new_outcome"], r["verdict"])
            for r in body["rows"]] == expect
    for r in body["rows"]:
        assert set(r) == {"pair_id", "position", "user_does", "device", "old_outcome", "new_outcome", "verdict"}
    assert body["rows"][1]["position"] == 4 and body["rows"][1]["user_does"] == "Cart"


def test_compare_without_with_uses_the_earlier_run(api, world, ran, rerun):
    plain = ok(api.get(f"/api/runs/{rerun.id}/compare"))
    explicit = ok(api.get(f"/api/runs/{rerun.id}/compare?with={ran.id}"))
    assert plain["rows"] == explicit["rows"] and plain["run"] == explicit["run"]


def test_compare_first_run_has_nothing_to_compare_to(api, world, ran):
    body = ok(api.get(f"/api/runs/{ran.id}/compare"))
    assert body["old_run"] is None and len(body["rows"]) == 14
    assert all(r["old_outcome"] is None and r["verdict"] == "same" for r in body["rows"])


@pytest.fixture
def third(env, world, ran, rerun):
    """Run 3: the shop broke again. Re-runs `cart` (last tested in run 2) and `search` (last tested in run 1)."""
    env.site.version = "broken"
    return run_everything(env.api, world, {"kind": "changed", "pair_ids": [world.ids["cart"], world.ids["search"]]})


def test_compare_without_with_uses_the_most_recent_earlier_run_that_tested_each_pair(api, world, ran, rerun, third):
    body = ok(api.get(f"/api/runs/{third.id}/compare"))
    assert body["run"] == third.info
    got = {(world.names[r["pair_id"]], r["device"]): (r["old_outcome"], r["new_outcome"], r["verdict"])
           for r in body["rows"]}
    assert got == {
        ("cart", "phone"): ("pass", "pass", "same"),
        ("cart", "laptop"): ("pass", "fail", "BROKE"),  # compared with run 2 (pass), not run 1 (fail)
        ("search", "phone"): ("pass", "pass", "same"),  # run 2 did not test it: falls back to run 1
        ("search", "laptop"): ("pass", "pass", "same"),
    }
    # with an explicit run the old run is exactly that run
    old = ok(api.get(f"/api/runs/{third.id}/compare?with={ran.id}"))
    assert old["old_run"] == ran.info
    assert {(world.names[r["pair_id"]], r["device"]): r["verdict"] for r in old["rows"]}[("cart", "laptop")] == "same"


def test_third_run_lists_both_earlier_runs_newest_first(api, ran, rerun, third):
    body = ok(api.get(f"/api/runs/{third.id}"))
    assert [r["run_number"] for r in body["earlier_runs"]] == [2, 1]
    assert third.info["run_number"] == 3


def test_compare_errors(api, world, ran, rerun):
    assert err(api.get(f"/api/runs/{rerun.id}/compare?with={uuid.uuid4()}"), 404)
    err(api.get(f"/api/runs/{uuid.uuid4()}/compare"), 404)
    other = new_project(api, site_url="https://other.example.com")
    new_pair(api, other, "x", "/", [chk("status_ok")], approved=True)
    foreign = ok(api.post(f"/api/projects/{other}/runs", {"kind": "full"}), 201)["run"]
    assert err(api.get(f"/api/runs/{rerun.id}/compare?with={foreign['id']}"), 400) == \
        "You can only compare runs of the same site."


# ================================================================ the fake database itself

class TestFakeDb:
    """The fake has to be as strict as Supabase, or the API tests above prove nothing."""

    @pytest.fixture
    def dbs(self):
        store = FakeStore()
        return FakeDb(TOK_A, store), FakeDb(TOK_B, store), store

    @staticmethod
    def seed(db):
        p = db.insert("projects", {"name": "P", "site_url": "https://p.example.com"})[0]
        g = db.insert("golden_pairs", {"project_id": p["id"], "position": 1, "user_does": "u", "good_result": "g"})[0]
        c = db.insert("checks", {"golden_pair_id": g["id"], "decided_by": "code", "rule": "status_ok"})[0]
        r = db.insert("runs", {"project_id": p["id"], "run_number": 1})[0]
        x = db.insert("results", {"run_id": r["id"], "golden_pair_id": g["id"], "device": "phone", "outcome": "pass"})[0]
        rc = db.insert("result_checks", {"result_id": x["id"], "check_id": c["id"]})[0]
        return p, g, c, r, x, rc

    def test_defaults_are_filled_like_the_sql(self, dbs):
        a, _, store = dbs
        p, g, c, r, x, rc = self.seed(a)
        assert p["user_id"] == USER_A and is_uuid(p["id"]) and p["created_at"]
        assert (g["method"], g["source"], g["approved"], g["is_priority"]) == ("GET", "builder", False, False)
        assert g["request_url"] is None and g["request_body"] is None
        assert (r["kind"], r["passed"], r["total"]) == ("full", 0, 0) and r["started_at"]
        assert (rc["passed"], rc["why"]) == (None, None) and (x["status_code"], x["what_site_said"]) == (None, None)
        stamps = [store.now() for _ in range(3)]
        assert stamps == sorted(stamps) and len(set(stamps)) == 3

    def test_unique_and_check_rules(self, dbs):
        a, _, _ = dbs
        p, g, c, r, x, rc = self.seed(a)
        with pytest.raises(SupaError) as e:
            a.insert("runs", {"project_id": p["id"], "run_number": 1})
        assert (e.value.status, e.value.code) == (409, "23505")
        with pytest.raises(SupaError) as e:
            a.insert("results", {"run_id": r["id"], "golden_pair_id": g["id"], "device": "phone", "outcome": "fail"})
        assert e.value.code == "23505"
        with pytest.raises(SupaError) as e:
            a.insert("result_checks", {"result_id": x["id"], "check_id": c["id"]})
        assert e.value.code == "23505"
        a.insert("diagnosis_points", {"run_id": r["id"], "result_id": x["id"], "rank": 1, "explanation": "e"})
        with pytest.raises(SupaError) as e:
            a.insert("diagnosis_points", {"run_id": r["id"], "result_id": x["id"], "rank": 1, "explanation": "e"})
        assert e.value.code == "23505"
        for rank in (0, 4):
            with pytest.raises(SupaError) as e:
                a.insert("diagnosis_points", {"run_id": r["id"], "result_id": x["id"], "rank": rank, "explanation": "e"})
            assert (e.value.status, e.value.code) == (500, "23514")
        with pytest.raises(SupaError) as e:  # a bad enum value
            a.insert("results", {"run_id": r["id"], "golden_pair_id": g["id"], "device": "tablet", "outcome": "pass"})
        assert e.value.code == "23514"
        with pytest.raises(SupaError) as e:  # NOT NULL
            a.insert("golden_pairs", {"project_id": p["id"], "user_does": "u", "good_result": "g"})
        assert e.value.code == "23502"
        with pytest.raises(SupaError) as e:  # a column that does not exist
            a.insert("projects", {"name": "x", "site_url": "y", "colour": "red"})
        assert e.value.code == "PGRST204"

    def test_a_failed_batch_inserts_nothing(self, dbs):
        a, _, store = dbs
        p, g, *_ = self.seed(a)
        with pytest.raises(SupaError):
            a.insert("checks", [{"golden_pair_id": g["id"], "decided_by": "code", "rule": "status_ok"},
                                {"golden_pair_id": g["id"], "decided_by": "code", "rule": "bogus"}])
        assert store.count("checks") == 1

    def test_results_and_manual_checks_follow_the_policies(self, dbs):
        a, _, store = dbs
        p, g, c, r, x, rc = self.seed(a)
        assert a.update("results", {"outcome": "fail"}, id=f"eq.{x['id']}") == []
        assert a.delete("results", id=f"eq.{x['id']}") == []
        assert store["results"][0]["outcome"] == "pass"
        assert a.delete("runs", id=f"eq.{r['id']}") == []
        assert a.update("result_checks", {"passed": True, "why": "ok"}, id=f"eq.{rc['id']}")[0]["passed"] is True
        assert a.update("result_checks", {"passed": False}, id=f"eq.{rc['id']}") == []  # already answered
        assert store["result_checks"][0]["passed"] is True
        assert a.update("runs", {"passed": 3, "total": 4}, id=f"eq.{r['id']}")[0]["total"] == 4

    def test_rls_hides_and_blocks_other_users(self, dbs):
        a, b, store = dbs
        p, g, c, r, x, rc = self.seed(a)
        for table in ("projects", "golden_pairs", "checks", "runs", "results", "result_checks"):
            assert b.select(table) == []
        assert b.one("projects", id=f"eq.{p['id']}") is None
        assert b.update("golden_pairs", {"approved": True}, id=f"eq.{g['id']}") == []
        assert b.delete("checks", golden_pair_id=f"eq.{g['id']}") == []
        assert store.count("checks") == 1 and store["golden_pairs"][0]["approved"] is False
        for table, row in [("golden_pairs", {"project_id": p["id"], "position": 2, "user_does": "u", "good_result": "g"}),
                           ("runs", {"project_id": p["id"], "run_number": 2}),
                           ("checks", {"golden_pair_id": g["id"], "decided_by": "code", "rule": "status_ok"}),
                           ("results", {"run_id": r["id"], "golden_pair_id": g["id"], "device": "laptop",
                                        "outcome": "pass"})]:
            with pytest.raises(SupaError) as e:
                b.insert(table, row)
            assert (e.value.status, e.value.code) == (404, "42501")
        with pytest.raises(SupaError) as e:
            FakeDb("tok-nobody", store).select("projects")
        assert e.value.status == 401

    def test_a_result_cannot_use_a_pair_of_another_project(self, dbs):
        a, _, _ = dbs
        p, g, c, r, x, rc = self.seed(a)
        p2 = a.insert("projects", {"name": "Q", "site_url": "https://q.example.com"})[0]
        g2 = a.insert("golden_pairs", {"project_id": p2["id"], "position": 1, "user_does": "u", "good_result": "g"})[0]
        with pytest.raises(SupaError) as e:
            a.insert("results", {"run_id": r["id"], "golden_pair_id": g2["id"], "device": "laptop", "outcome": "pass"})
        assert e.value.code == "42501"

    def test_filters_order_limit_and_embeds(self, dbs):
        a, _, _ = dbs
        p, g, c, r, x, rc = self.seed(a)
        g2 = a.insert("golden_pairs", {"project_id": p["id"], "position": 2, "user_does": "u2", "good_result": "g2",
                                       "approved": True})[0]
        a.insert("checks", [{"golden_pair_id": g2["id"], "decided_by": "code", "rule": "status_ok"},
                            {"golden_pair_id": g2["id"], "decided_by": "ai", "rule": "ai_judge", "expected": "q?"}])
        assert [x["position"] for x in a.select("golden_pairs", order="position.desc")] == [2, 1]
        assert [x["position"] for x in a.select("golden_pairs", order="position.asc", limit="1")] == [1]
        assert [x["id"] for x in a.select("golden_pairs", approved="is.true")] == [g2["id"]]
        assert len(a.select("golden_pairs", id=f"in.({g['id']},{g2['id']})")) == 2
        assert a.select("golden_pairs", id="in.()") == []
        assert a.select("golden_pairs", position="lt.2")[0]["id"] == g["id"]
        assert a.select("golden_pairs", position="eq.2", select="id,position") == [{"id": g2["id"], "position": 2}]
        pair = a.one("golden_pairs", id=f"eq.{g2['id']}", select="*,checks(*)")
        assert pair["user_does"] == "u2" and [k["rule"] for k in pair["checks"]] == ["status_ok", "ai_judge"]
        res = a.one("results", id=f"eq.{x['id']}",
                    select="*,golden_pairs(position,user_does,good_result,is_priority),"
                           "result_checks(id,check_id,passed,why,checks(decided_by,rule,expected,created_at))")
        assert res["golden_pairs"] == {"position": 1, "user_does": "u", "good_result": "g", "is_priority": False}
        (rcheck,) = res["result_checks"]
        assert set(rcheck) == {"id", "check_id", "passed", "why", "checks"} and rcheck["checks"]["rule"] == "status_ok"
        assert set(rcheck["checks"]) == {"decided_by", "rule", "expected", "created_at"}
        got = a.one("result_checks", id=f"eq.{rc['id']}", select="id,passed,why,check_id,checks(decided_by,rule,expected)")
        assert got["checks"] == {"decided_by": "code", "rule": "status_ok", "expected": None}
        with pytest.raises(NotImplementedError):
            a.select("golden_pairs", position="gte.1")

    def test_cascade_delete_of_checks_removes_their_result_checks(self, dbs):
        a, _, store = dbs
        p, g, c, r, x, rc = self.seed(a)
        assert [d["id"] for d in a.delete("checks", golden_pair_id=f"eq.{g['id']}")] == [c["id"]]
        assert store["result_checks"] == []

    def test_returned_rows_are_copies(self, dbs):
        a, _, store = dbs
        p, *_ = self.seed(a)
        p["name"] = "changed by the caller"
        got = a.select("projects")[0]
        got["name"] = "again"
        assert store["projects"][0]["name"] == "P"
