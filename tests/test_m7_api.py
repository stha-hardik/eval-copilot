"""M7 · the real browser, tested end to end through the API doors (api/index.py).

Nothing leaves this machine: Supabase is tests/fake_db.py, the plain page read is FakeSite (test_api.py), the
text AI is FakeGroq (test_api.py), and the two new outside helpers are faked HERE:
  * FakeBrowser replaces `browser.run`: scripted `browser.Session` objects, and it records every call
    (device, steps, flags, order, start and end times) so the tests can check the routing rules.
  * FakeVision replaces `groq.judge_screenshot`.
`site.run_code_check`, `site.excerpt`, `index._judge_device`, `groq.normalize_draft` and (in one test) the real
`groq.judge_screenshot` stay REAL.

The rules under test (from the owner's spec): code decides in a fixed order. Fetch for status_ok / text_has /
text_absent / min_results / count_equals / ai_judge; browser for browser_count / ai_vision (one session per pair +
device, one screenshot for all the vision checks); a thin or JavaScript-only page is retried once in the browser;
a person only for login / captcha / payment, vision unsure twice, Browserless trouble, or the 12-session run cap.
"""
from __future__ import annotations

import json
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from test_api import (  # noqa: F401  (the fixtures `env` and `api` are used by name)
    BLOCKED_WHY, SITE_URL, api, env, err, html, new_pair, new_project, ok,
)
import index  # noqa: E402  (api/index.py, already on the path through test_api)

browser = index.browser
groq = index.groq
site = index.site
REAL_TIDY, REAL_CHANGE, REAL_SUGGEST = groq.tidy_pair, groq.change_to_pair, groq.suggest_pairs
REAL_JUDGE_SHOT = groq.judge_screenshot
HUMAN = browser.HUMAN

LONG = html("Solaris", "<h1>Solaris lamp</h1><p>" + "A warm reading lamp for your desk. " * 20 + "</p>")  # > 300 chars
THIN = html("Loading", "<p>Loading</p>")  # < 300 chars
STEPS = [{"goto": "/products/solaris"}, {"click": "text=Sand"}]
CART_1 = {"token": "t", "item_count": 1, "currency": "EUR", "total_price": 7900,
          "items": [{"product_title": "Solaris", "variant_title": "Sand", "quantity": 1, "final_price": 7900}]}
CART_5 = {**CART_1, "item_count": 5, "total_price": 39500,
          "items": [{**CART_1["items"][0], "quantity": 5}]}
VISION_OK = {"passed": True, "why": "I can see it on the screen.", "confident": True}


# ---------------------------------------------------------------- the two fakes

# Hand-overs where no hosted browser was ever opened (no units used).
NOT_RUN = {browser.HUMAN[k] for k in ("no_token", "bad_token", "busy", "units", "down", "time", "cap")}


class FakeBrowser:
    """Stands in for browser.run. `make(call)` returns the Session for a call (override per test)."""

    def __init__(self):
        self.calls: list[SimpleNamespace] = []
        self.make = self.default
        self.delay = 0.02  # a real pause, so two sessions that overlapped in time would be caught
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    @staticmethod
    def default(call) -> browser.Session:
        return browser.Session(
            device=call.device, status_code=200, url=SITE_URL + call.start_path,
            text="Solaris lamp. Sand is selected. " * 12,
            cart=CART_1 if call.want_cart else None, shot=f"SHOT-{call.device}" if call.want_shot else None,
            notes=["opened /products/solaris", "clicked Sand"])

    def run(self, site_url, start_path, steps, device, want_shot, want_cart, want_html=False, budget_s=45):
        call = SimpleNamespace(site_url=site_url, start_path=start_path, steps=steps, device=device,
                               want_shot=want_shot, want_cart=want_cart, want_html=want_html, budget_s=budget_s)
        with self.lock:
            call.seq = len(self.calls)
            self.calls.append(call)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        call.t0 = time.monotonic()
        time.sleep(self.delay)
        session = self.make(call)
        if not session.ran and session.human_reason not in NOT_RUN:
            session.ran = True  # like browser.run: a hosted browser opened (it uses units)
        call.t1 = time.monotonic()
        with self.lock:
            self.active -= 1
        return session

    def devices(self) -> list[str]:
        return [c.device for c in self.calls]


class FakeVision:
    """Stands in for groq.judge_screenshot. `answer(device, checks)` returns {check_id: verdict} (override per test)."""

    def __init__(self):
        self.calls: list[SimpleNamespace] = []
        self.answer = lambda device, checks: {c["id"]: dict(VISION_OK) for c in checks}
        self.lock = threading.Lock()

    def judge_screenshot(self, shot_b64, pair, checks, device, timeout=25):
        with self.lock:
            self.calls.append(SimpleNamespace(shot=shot_b64, pair_id=pair["id"], ids=[c["id"] for c in checks],
                                              questions=[c["expected"] for c in checks], device=device,
                                              timeout=timeout))
        if not shot_b64:  # like the real judge: no picture, no verdict
            return {c["id"]: {"passed": None, "why": "no picture", "confident": False} for c in checks}
        return self.answer(device, checks)


@pytest.fixture(autouse=True)
def no_browserless_env(monkeypatch):
    """A Browserless key on the machine must never let a test reach the network."""
    for name in list(os.environ):
        if "BROWSERLESS" in name.upper():
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def m7(env, monkeypatch):
    env.fb, env.fv = FakeBrowser(), FakeVision()
    monkeypatch.setattr(index.browser, "run", env.fb.run)
    monkeypatch.setattr(index.groq, "judge_screenshot", env.fv.judge_screenshot)
    return env


# ---------------------------------------------------------------- builders

def C(rule, expected=None, steps=None):
    return {"rule": rule, "expected": expected, "steps": steps}


def long_pages(m7, *urls):
    for u in urls:
        m7.site.overrides[u] = (200, LONG)


def mk(m7, pid, name, url, checks, **extra):
    """An approved pair; GET pages are long (no render fallback) unless the test says otherwise."""
    if url not in m7.site.overrides and "/cart/" not in url and url not in ("/blocked", "/broken", "/slow"):
        m7.site.overrides[url] = (200, LONG)
    return new_pair(m7.api, pid, name, url, checks, approved=True, **extra)


def drive(api, pid, body=None) -> SimpleNamespace:
    """Door 8, door 9 for every pair (in the order the API gives), door 10."""
    started = ok(api.post(f"/api/projects/{pid}/runs", body or {"kind": "full"}), 201)
    run_id, rows = started["run"]["id"], {}
    for pair_id in started["pair_ids"]:
        rows[pair_id] = ok(api.post(f"/api/runs/{run_id}/pairs/{pair_id}"), 201)["rows"]
    done = ok(api.post(f"/api/runs/{run_id}/finish"))
    return SimpleNamespace(id=run_id, order=started["pair_ids"], rows=rows, done=done)


def dev(rows) -> dict:
    return {r["device"]: r for r in rows}


def check_of(row, rule) -> dict:
    return next(c for c in row["checks"] if c["rule"] == rule)


def checks_of(row, rule) -> list[dict]:
    return [c for c in row["checks"] if c["rule"] == rule]


def store_text(m7) -> str:
    return json.dumps({k: v for k, v in m7.store.items()}, default=str)


@pytest.fixture
def pid(m7):
    return new_project(m7.api)


# ================================================================ 1 · fetch rules never open a browser

def test_fetch_only_pair_makes_no_browser_call(m7, pid):
    mk(m7, pid, "Reads the lamp page", "/products/solaris",
       [C("status_ok"), C("text_has", "Solaris"), C("text_absent", "Oops"), C("count_equals", "Solaris=1"),
        C("ai_judge", "Does the page show the Solaris lamp?")])
    r = drive(m7.api, pid)
    assert m7.fb.calls == [] and m7.fv.calls == []
    for rows in r.rows.values():
        assert [x["device"] for x in rows] == ["phone", "laptop"]
        for row in rows:
            assert row["via"] == "fetch" and row["human_reason"] == ""
            assert not row["what_site_said"].startswith("Real browser")


def test_a_short_page_with_only_status_ok_is_not_retried(m7, pid):
    m7.site.overrides["/thin"] = (200, THIN)
    mk(m7, pid, "Page loads", "/thin", [C("status_ok")])
    drive(m7.api, pid)
    assert m7.fb.calls == []


def test_two_fetch_pairs_and_one_browser_pair_open_only_the_browser_pairs_sessions(m7, pid):
    mk(m7, pid, "Plain", "/products/a", [C("status_ok"), C("text_has", "Solaris")])
    mk(m7, pid, "Looks", "/products/b", [C("status_ok"), C("ai_vision", "Is the menu open?", STEPS)])
    mk(m7, pid, "Plain 2", "/products/c", [C("status_ok")])
    drive(m7.api, pid)
    assert m7.fb.devices() == ["phone", "laptop"]


# ================================================================ 2 · browser rules: one session per device

@pytest.fixture
def lamp(m7, pid):
    """One pair with fetch + browser checks. Two vision checks and a cart count, as the owner described."""
    pair = mk(m7, pid, "Picks Sand and adds it", "/products/solaris",
              [C("status_ok"), C("ai_vision", "Is the Sand image showing?", STEPS),
               C("ai_vision", "Is the cart preview lit up?", [{"goto": "/"}]),
               C("browser_count", "item_count=1", [{"goto": "/other"}])])
    return SimpleNamespace(pair=pair, id=pair["id"], checks=pair["checks"])


def test_browser_pair_opens_exactly_two_sessions_phone_then_laptop_never_overlapping(m7, pid, lamp):
    drive(m7.api, pid)
    assert m7.fb.devices() == ["phone", "laptop"]
    assert m7.fb.max_active == 1
    phone, laptop = m7.fb.calls
    assert phone.t1 <= laptop.t0  # the phone session finished before the laptop one started


def test_session_gets_first_browser_checks_steps_and_both_flags(m7, pid, lamp):
    drive(m7.api, pid)
    for call in m7.fb.calls:
        assert call.steps == [{"goto": "/products/solaris"}, {"click": "text=Sand"}]
        assert call.want_shot is True and call.want_cart is True and call.want_html is False
        assert call.start_path == "/products/solaris" and call.site_url == SITE_URL
        assert 0 < call.budget_s <= index.DOOR_BUDGET - index.GROQ_RESERVE


def test_one_vision_call_per_device_with_all_vision_checks_and_that_devices_screenshot(m7, pid, lamp):
    drive(m7.api, pid)
    vision_ids = [c["id"] for c in lamp.checks if c["rule"] == "ai_vision"]
    assert len(m7.fv.calls) == 2
    assert {c.device for c in m7.fv.calls} == {"phone", "laptop"}
    for call in m7.fv.calls:
        assert call.ids == vision_ids and call.pair_id == lamp.id
        assert call.questions == ["Is the Sand image showing?", "Is the cart preview lit up?"]
        assert call.shot == f"SHOT-{call.device}"


def test_rows_say_browser_and_browser_count_passes_with_one_item(m7, pid, lamp):
    r = drive(m7.api, pid)
    rows = dev(r.rows[lamp.id])
    for d in ("phone", "laptop"):
        row = rows[d]
        assert row["via"] == "browser" and row["human_reason"] == "" and row["outcome"] == "pass"
        assert row["why"] == "" and row["status_code"] == 200
        assert row["what_site_said"].startswith("Real browser")
        assert len(row["what_site_said"]) <= 500
        assert [c["passed"] for c in row["checks"]] == [True, True, True, True]
        assert check_of(row, "ai_vision")["why"] == VISION_OK["why"]
    assert r.done["run"]["passed"] == 2 and r.done["run"]["total"] == 2


def test_browser_count_fails_with_five_items_and_the_reason_mentions_five(m7, pid, lamp):
    m7.fb.make = lambda call: FakeBrowser.default(call) if call.device == "phone" else browser.Session(
        device="laptop", status_code=200, url=SITE_URL, text="x", cart=CART_5, shot="SHOT-laptop")
    r = drive(m7.api, pid)
    rows = dev(r.rows[lamp.id])
    assert rows["phone"]["outcome"] == "pass"
    lap = rows["laptop"]
    assert lap["outcome"] == "fail" and lap["via"] == "browser"
    bad = check_of(lap, "browser_count")
    assert bad["passed"] is False and "5" in bad["why"]
    assert "5" in lap["why"]
    assert "Cart has 5 items" in lap["what_site_said"]
    assert [c["passed"] for c in lap["checks"] if c["rule"] != "browser_count"] == [True, True, True]


def test_what_site_said_keeps_the_note_and_the_cart_line_but_never_the_screenshot(m7, pid, lamp):
    r = drive(m7.api, pid)
    for row in r.rows[lamp.id]:
        assert row["what_site_said"].startswith("Real browser")
        assert "clicked Sand" in row["what_site_said"]
    assert "SHOT-phone" not in store_text(m7) and "SHOT-laptop" not in store_text(m7)
    assert "SHOT-" not in json.dumps(ok(m7.api.get(f"/api/runs/{r.id}")))


def test_only_browser_count_asks_for_a_cart_and_no_screenshot(m7, pid):
    mk(m7, pid, "Count", "/products/solaris", [C("status_ok"), C("browser_count", "item_count=1", STEPS)])
    drive(m7.api, pid)
    assert [(c.want_shot, c.want_cart) for c in m7.fb.calls] == [(False, True), (False, True)]
    assert m7.fv.calls == []


def test_only_vision_asks_for_a_screenshot_and_no_cart(m7, pid):
    mk(m7, pid, "Look", "/products/solaris", [C("status_ok"), C("ai_vision", "Is the menu open?", STEPS)])
    drive(m7.api, pid)
    assert [(c.want_shot, c.want_cart) for c in m7.fb.calls] == [(True, False), (True, False)]
    assert len(m7.fv.calls) == 2


def test_browser_check_without_steps_opens_the_pairs_own_page(m7, pid):
    mk(m7, pid, "Look", "/products/solaris", [C("ai_vision", "Is it nice?")])
    drive(m7.api, pid)
    assert [c.steps for c in m7.fb.calls] == [[{"goto": "/products/solaris"}]] * 2
    assert {c.start_path for c in m7.fb.calls} == {"/products/solaris"}


def test_post_pair_with_a_browser_check_starts_the_browser_on_the_home_page(m7, pid):
    new_pair(m7.api, pid, "Adds to cart", "/cart/add.js", [C("status_ok"), C("browser_count", "item_count=1")],
             approved=True, method="POST", request_body={"items": [{"handle": "solaris", "quantity": 1}]})
    drive(m7.api, pid)
    assert [(c.start_path, c.steps) for c in m7.fb.calls] == [("/", [{"goto": "/"}])] * 2


def test_the_vision_judge_gets_each_sessions_own_device_name(m7, pid, lamp):
    drive(m7.api, pid)
    assert sorted(c.device for c in m7.fv.calls) == ["laptop", "phone"]


def test_vision_fail_is_a_fail_with_the_ais_reason(m7, pid):
    mk(m7, pid, "Look", "/products/solaris", [C("status_ok"), C("ai_vision", "Is the text readable?", STEPS)])
    m7.fv.answer = lambda device, checks: {c["id"]: {"passed": device != "phone", "why": f"{device}: text overlaps",
                                                      "confident": True} for c in checks}
    r = drive(m7.api, pid)
    rows = dev(next(iter(r.rows.values())))
    assert rows["phone"]["outcome"] == "fail" and rows["phone"]["why"] == "phone: text overlaps"
    assert rows["laptop"]["outcome"] == "pass"
    assert rows["phone"]["via"] == "browser"


def test_second_call_of_door_9_does_not_open_more_sessions(m7, pid, lamp):
    r = drive(m7.api, pid)
    again = ok(m7.api.post(f"/api/runs/{r.id}/pairs/{lamp.id}"), 201)["rows"]
    assert len(m7.fb.calls) == 2 and len(m7.fv.calls) == 2
    assert [x["result_id"] for x in again] == [x["result_id"] for x in r.rows[lamp.id]]


# ================================================================ 3 · payment / login / captcha -> a person

@pytest.mark.parametrize("key", ["payment", "login", "captcha"])
def test_page_that_needs_a_person_hands_the_browser_checks_over(m7, pid, key):
    pair = mk(m7, pid, "Checks out", "/products/solaris",
              [C("status_ok"), C("ai_vision", "Is the checkout button clear?", STEPS), C("browser_count", "item_count=1")])
    m7.fb.make = lambda call: browser.Session(device=call.device, human_reason=HUMAN[key])
    r = drive(m7.api, pid)
    for row in r.rows[pair["id"]]:
        assert row["via"] == "human" and row["human_reason"] == HUMAN[key]
        assert row["outcome"] == "pass" and row["why"] == ""  # status_ok passed: a person is NOT a failure
        for rule in ("ai_vision", "browser_count"):
            c = check_of(row, rule)
            assert c["passed"] is None and c["why"] == HUMAN[key]
        assert check_of(row, "status_ok")["passed"] is True
    assert m7.fv.calls == []  # no screenshot was judged
    assert r.done["run"]["passed"] == 2


def test_payment_reason_text_is_the_one_in_the_spec(m7, pid):
    assert HUMAN["payment"] == "Payment page, a person needs to check this"


def test_only_browser_checks_at_payment_make_the_result_cant_test_with_the_reason_as_why(m7, pid):
    pair = mk(m7, pid, "Pays", "/products/solaris", [C("ai_vision", "Does it look right?", STEPS)])
    m7.fb.make = lambda call: browser.Session(device=call.device, human_reason=HUMAN["payment"])
    row = drive(m7.api, pid).rows[pair["id"]][0]
    assert row["outcome"] == "cant_test" and row["why"] == HUMAN["payment"] and row["via"] == "human"
    assert row["human_reason"] == HUMAN["payment"]


def test_one_device_at_payment_and_the_other_fine(m7, pid):
    pair = mk(m7, pid, "Cart", "/products/solaris", [C("status_ok"), C("browser_count", "item_count=1", STEPS)])
    m7.fb.make = lambda call: (browser.Session(device="phone", human_reason=HUMAN["payment"])
                               if call.device == "phone" else FakeBrowser.default(call))
    rows = dev(drive(m7.api, pid).rows[pair["id"]])
    assert rows["phone"]["via"] == "human" and rows["phone"]["human_reason"] == HUMAN["payment"]
    assert rows["laptop"]["via"] == "browser" and rows["laptop"]["human_reason"] == ""
    assert rows["laptop"]["outcome"] == "pass"


def test_door_13_lets_a_person_answer_the_handed_over_check(m7, pid):
    pair = mk(m7, pid, "Checks out", "/products/solaris", [C("status_ok"), C("ai_vision", "Is it clear?", STEPS)])
    m7.fb.make = lambda call: browser.Session(device=call.device, human_reason=HUMAN["payment"])
    r = drive(m7.api, pid)
    row = dev(r.rows[pair["id"]])["phone"]
    target = check_of(row, "ai_vision")
    answered = ok(m7.api.patch(f"/api/result-checks/{target['id']}", {"passed": True}))["check"]
    assert answered["passed"] is True and answered["why"] == "You said it looks right."
    assert answered["rule"] == "ai_vision" and answered["decided_by"] == "ai"
    err(m7.api.patch(f"/api/result-checks/{target['id']}", {"passed": False}), 409)  # one answer only
    # the other device's check is answered separately
    laptop = dev(r.rows[pair["id"]])["laptop"]
    other = check_of(laptop, "ai_vision")
    assert ok(m7.api.patch(f"/api/result-checks/{other['id']}", {"passed": False}))["check"]["why"] == \
        "You said it looks wrong."


@pytest.mark.parametrize("key", ["no_token", "bad_token", "busy", "units", "down", "slow", "time"])
def test_every_browserless_trouble_hands_over_with_its_reason(m7, pid, key):
    pair = mk(m7, pid, "Look", "/products/solaris", [C("status_ok"), C("ai_vision", "Is it nice?", STEPS)])
    m7.fb.make = lambda call: browser.Session(device=call.device, human_reason=HUMAN[key])
    for row in drive(m7.api, pid).rows[pair["id"]]:
        assert row["via"] == "human" and row["human_reason"] == HUMAN[key]
        assert check_of(row, "ai_vision")["passed"] is None
        assert row["outcome"] == "pass"


def test_without_a_browserless_key_the_real_browser_module_hands_over_and_makes_no_http_call(env, monkeypatch):
    """No fake browser here: the real browser.run runs and finds no token."""
    def boom(*a, **k):
        raise AssertionError("no HTTP call is allowed without a token")
    monkeypatch.setattr(requests, "post", boom)
    monkeypatch.setattr(index.groq, "judge_screenshot", lambda *a, **k: pytest.fail("no screenshot exists"))
    p = new_project(env.api)
    pair = new_pair(env.api, p, "Look", "/products/solaris", [C("status_ok"), C("ai_vision", "Is it nice?", STEPS)],
                    approved=True)
    env.site.overrides["/products/solaris"] = (200, LONG)
    for row in drive(env.api, p).rows[pair["id"]]:
        assert row["via"] == "human" and row["human_reason"] == HUMAN["no_token"] and row["outcome"] == "pass"


# ================================================================ 4 · vision not sure -> a person

def test_vision_not_confident_is_passed_none_with_the_unsure_text(m7, pid):
    pair = mk(m7, pid, "Look", "/products/solaris", [C("status_ok"), C("ai_vision", "Is it nice?", STEPS)])
    m7.fv.answer = lambda device, checks: {c["id"]: {"passed": None, "why": "can't tell", "confident": False}
                                           for c in checks}
    r = drive(m7.api, pid)
    for row in r.rows[pair["id"]]:
        c = check_of(row, "ai_vision")
        assert c["passed"] is None and c["why"] == index.VISION_UNSURE
        assert row["via"] == "human" and row["human_reason"] == index.VISION_UNSURE
        assert row["outcome"] == "pass"  # the fetch check passed; the unsure one waits for a person


def test_unsure_with_a_guess_in_passed_is_still_not_trusted(m7, pid):
    pair = mk(m7, pid, "Look", "/products/solaris", [C("ai_vision", "Is it nice?", STEPS)])
    m7.fv.answer = lambda device, checks: {c["id"]: {"passed": False, "why": "maybe", "confident": False}
                                           for c in checks}
    row = drive(m7.api, pid).rows[pair["id"]][0]
    assert check_of(row, "ai_vision")["passed"] is None and row["outcome"] == "cant_test"
    assert row["why"] == index.VISION_UNSURE


def test_vision_with_a_missing_answer_is_unsure(m7, pid):
    pair = mk(m7, pid, "Look", "/products/solaris", [C("ai_vision", "Is it nice?", STEPS)])
    m7.fv.answer = lambda device, checks: {}
    row = drive(m7.api, pid).rows[pair["id"]][0]
    assert check_of(row, "ai_vision")["why"] == index.VISION_UNSURE and row["via"] == "human"


def test_missing_screenshot_is_handed_over_not_failed(m7, pid):
    pair = mk(m7, pid, "Look", "/products/solaris", [C("ai_vision", "Is it nice?", STEPS)])
    m7.fb.make = lambda call: browser.Session(device=call.device, status_code=200, url="u", text="t", shot=None)
    m7.fv.answer = lambda device, checks: {c["id"]: {"passed": None, "why": "x", "confident": False} for c in checks}
    row = drive(m7.api, pid).rows[pair["id"]][0]
    assert m7.fv.calls[0].shot == ""  # the judge is told there is no picture
    assert check_of(row, "ai_vision")["passed"] is None and row["via"] == "human"


def test_one_sure_and_one_unsure_vision_check_mix(m7, pid):
    pair = mk(m7, pid, "Look", "/products/solaris",
              [C("status_ok"), C("ai_vision", "Is the menu open?", STEPS), C("ai_vision", "Is the logo sharp?")])
    first = pair["checks"][1]["id"]

    def answer(device, checks):
        return {c["id"]: ({"passed": False, "why": "menu is closed", "confident": True} if c["id"] == first
                          else {"passed": None, "why": "?", "confident": False}) for c in checks}
    m7.fv.answer = answer
    row = dev(drive(m7.api, pid).rows[pair["id"]])["phone"]
    a, b = checks_of(row, "ai_vision")
    assert (a["passed"], a["why"]) == (False, "menu is closed")
    assert (b["passed"], b["why"]) == (None, index.VISION_UNSURE)
    assert row["outcome"] == "fail" and row["why"] == "menu is closed" and row["via"] == "human"
    assert row["human_reason"] == index.VISION_UNSURE


def test_real_judge_screenshot_asks_twice_and_only_about_the_unsure_check(m7, pid, monkeypatch):
    """The real groq.judge_screenshot inside the door, with Groq's HTTP mocked."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(index.groq, "judge_screenshot", REAL_JUDGE_SHOT)
    pair = mk(m7, pid, "Look", "/products/solaris",
              [C("status_ok"), C("ai_vision", "Is the menu open?", STEPS), C("ai_vision", "Is the logo sharp?")])
    v1, v2 = (c["id"] for c in pair["checks"][1:])
    seen: dict[str, list[list[str]]] = {"phone": [], "laptop": []}
    lock = threading.Lock()

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == groq.GROQ_URL and json["model"] == groq.VISION_MODEL
        text = json["messages"][1]["content"][0]["text"]
        info = __import__("json").loads(text)
        ids = [c["id"] for c in info["checks"]]
        assert json["messages"][1]["content"][1]["image_url"]["url"] == f"data:image/jpeg;base64,SHOT-{info['device']}"
        with lock:
            seen[info["device"]].append(ids)
            attempt = len(seen[info["device"]])
        if info["device"] == "phone":
            results = ([{"id": v1, "passed": True, "why": "menu open", "confident": True},
                        {"id": v2, "passed": True, "why": "blurry", "confident": False}] if attempt == 1 else
                       [{"id": v2, "passed": False, "why": "logo is blurry", "confident": True}])
        else:
            results = [{"id": i, "passed": True, "why": "?", "confident": False} for i in ids]
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"choices": [{"message": {"content": __import__("json").dumps({"results": results})}}]}
        return r

    monkeypatch.setattr(requests, "post", fake_post)
    rows = dev(drive(m7.api, pid).rows[pair["id"]])
    assert seen["phone"] == [[v1, v2], [v2]] and seen["laptop"] == [[v1, v2], [v1, v2]]
    ph = rows["phone"]
    assert [c["passed"] for c in checks_of(ph, "ai_vision")] == [True, False] and ph["outcome"] == "fail"
    assert ph["via"] == "browser" and ph["why"] == "logo is blurry"
    lap = rows["laptop"]
    assert [c["passed"] for c in checks_of(lap, "ai_vision")] == [None, None]
    assert lap["via"] == "human" and lap["human_reason"] == index.VISION_UNSURE and lap["outcome"] == "pass"


# ================================================================ 5 · the run cap: 12 sessions per run

def vision_pairs(m7, pid, n):
    for i in range(1, n + 1):
        mk(m7, pid, f"Pair {i}", f"/products/p{i}", [C("status_ok"), C("ai_vision", "Is it nice?", STEPS)])


def test_run_cap_is_twelve_sessions(m7, pid):
    assert browser.RUN_CAP == 12
    vision_pairs(m7, pid, 7)
    r = drive(m7.api, pid)
    assert len(m7.fb.calls) == 12  # pairs 1-6 (12 sessions); pair 7 is never opened
    assert len(m7.fv.calls) == 12
    for pair_id in r.order[:6]:
        for row in r.rows[pair_id]:
            assert row["via"] == "browser" and row["human_reason"] == ""
    for row in r.rows[r.order[6]]:  # the 13th and 14th sessions
        c = check_of(row, "ai_vision")
        assert c["passed"] is None and c["why"] == "Browser limit for this run reached" == HUMAN["cap"]
        assert row["via"] == "human" and row["human_reason"] == HUMAN["cap"]
        assert row["outcome"] == "pass"  # status_ok still passed
    assert r.done["run"]["total"] == 14 and r.done["run"]["passed"] == 14  # the run still finishes


def test_cap_applies_to_the_whole_run_not_to_one_pair_call(m7, pid):
    vision_pairs(m7, pid, 7)
    drive(m7.api, pid)
    assert [c.start_path for c in m7.fb.calls[-2:]] == ["/products/p6", "/products/p6"]


def test_a_new_run_gets_a_fresh_twelve(m7, pid):
    vision_pairs(m7, pid, 7)
    drive(m7.api, pid)
    m7.fb.calls.clear()
    r2 = drive(m7.api, pid)
    assert len(m7.fb.calls) == 12
    assert all(row["via"] == "human" for row in r2.rows[r2.order[6]])


def test_cap_hit_pair_with_a_single_device_left_to_run(m7, pid):
    """Eleven sessions used, then a pair needs two: the phone gets the 12th, the laptop is over the cap."""
    vision_pairs(m7, pid, 6)  # pairs 1-5 = 10 sessions
    extra = mk(m7, pid, "Last", "/products/last", [C("status_ok"), C("ai_vision", "Is it nice?", STEPS)])
    # put one pair of the five on only ONE finished device so the count becomes 11 before "Last"
    started = ok(m7.api.post(f"/api/projects/{pid}/runs", {"kind": "full"}), 201)
    run_id, order = started["run"]["id"], started["pair_ids"]
    for pair_id in order[:5]:
        ok(m7.api.post(f"/api/runs/{run_id}/pairs/{pair_id}"), 201)
    m7.store["results"].append({"id": "00000000-0000-4000-8000-0000000000aa", "run_id": run_id,
                                "golden_pair_id": order[5], "device": "phone", "status_code": 200,
                                "what_site_said": "Real browser · opened /", "outcome": "pass", "via": "browser",
                                "created_at": "z"})
    before = len(m7.fb.calls)
    rows = dev(ok(m7.api.post(f"/api/runs/{run_id}/pairs/{extra['id']}"), 201)["rows"])
    assert len(m7.fb.calls) - before == 1 and m7.fb.calls[-1].device == "phone"
    assert rows["phone"]["via"] == "browser" and rows["laptop"]["human_reason"] == HUMAN["cap"]


def test_manual_check_pairs_do_not_use_up_the_browser_cap(m7, pid):
    for i in range(1, 8):  # 7 pairs x 2 devices = 14 results via 'human', zero sessions
        mk(m7, pid, f"Manual {i}", f"/pages/m{i}", [C("status_ok"), C("manual", "Does it look friendly?")])
    mk(m7, pid, "Browser pair", "/products/solaris", [C("status_ok"), C("ai_vision", "Is it nice?", STEPS)])
    r = drive(m7.api, pid)
    assert len(m7.fb.calls) == 2
    assert all(row["via"] == "browser" for row in r.rows[r.order[-1]])


def test_render_fallback_sessions_that_fail_still_count_towards_the_cap(m7, pid):
    m7.site.overrides.update({f"/pages/t{i}": (200, THIN) for i in range(1, 9)})
    for i in range(1, 9):
        mk(m7, pid, f"Thin {i}", f"/pages/t{i}", [C("status_ok"), C("text_has", "Zzz")])
    m7.fb.make = lambda call: browser.Session(device=call.device, error='We couldn\'t find "x" to click on the page.')
    drive(m7.api, pid)
    assert len(m7.fb.calls) <= browser.RUN_CAP


def test_what_site_said_does_not_claim_a_browser_when_none_ran(m7, pid):
    pair = mk(m7, pid, "Look", "/products/solaris", [C("status_ok"), C("ai_vision", "Is it nice?", STEPS)])
    m7.fb.make = lambda call: browser.Session(device=call.device, human_reason=HUMAN["no_token"])
    for row in drive(m7.api, pid).rows[pair["id"]]:
        assert not row["what_site_said"].startswith("Real browser")


# ================================================================ 6 · plain read first, browser only if the page is empty

@pytest.fixture
def thin(m7, pid):
    m7.site.overrides["/pages/app"] = (200, THIN)
    pair = mk(m7, pid, "Reads the page", "/pages/app", [C("status_ok"), C("text_has", "Sand")])
    m7.fb.make = lambda call: browser.Session(device=call.device, status_code=200, url=SITE_URL + "/pages/app",
                                              text="Solaris in Sand and Black. " * 20, notes=["opened /pages/app"])
    return pair


def test_thin_page_is_retried_once_per_device_in_the_browser(m7, pid, thin):
    r = drive(m7.api, pid)
    assert m7.fb.devices() == ["phone", "laptop"] and m7.fb.max_active == 1
    for call in m7.fb.calls:
        assert call.want_html is True and call.want_shot is False and call.want_cart is False
        assert call.steps == [{"goto": "/pages/app"}] and call.start_path == "/pages/app"
    for row in r.rows[thin["id"]]:
        assert row["via"] == "browser" and row["outcome"] == "pass"
        assert check_of(row, "text_has")["passed"] is True  # the word is only in the rendered text
        assert row["what_site_said"].startswith("Real browser")
        assert row["status_code"] == 200  # the plain read's status stays the result's status


def test_the_rendered_text_can_also_fail_the_text_check(m7, pid, thin):
    m7.fb.make = lambda call: browser.Session(device=call.device, status_code=200, url="u",
                                              text="Only Black here. " * 30)
    for row in drive(m7.api, pid).rows[thin["id"]]:
        assert row["via"] == "browser" and row["outcome"] == "fail"
        assert check_of(row, "text_has")["passed"] is False


def test_rendered_text_answers_ai_judge_too(m7, pid):
    m7.site.overrides["/pages/app"] = (200, THIN)
    pair = mk(m7, pid, "Reads", "/pages/app", [C("status_ok"), C("ai_judge", "Does the page show the Solaris lamp?")])
    m7.fb.make = lambda call: browser.Session(device=call.device, status_code=200, url="u", text="Solaris lamp " * 40)
    for row in drive(m7.api, pid).rows[pair["id"]]:
        assert row["via"] == "browser" and check_of(row, "ai_judge")["passed"] is True
        assert check_of(row, "ai_judge")["why"].startswith("AI:")


def test_js_shell_with_enough_text_is_also_retried(m7, pid):
    shell = html("App", '<div id="root"></div><p>' + "Menu item. " * 60 + "</p>")
    m7.site.overrides["/app"] = (200, shell)
    pair = mk(m7, pid, "App", "/app", [C("status_ok"), C("text_has", "Sand")])
    m7.fb.make = lambda call: browser.Session(device=call.device, status_code=200, url="u", text="Sand " * 5)
    rows = drive(m7.api, pid).rows[pair["id"]]
    assert len(m7.fb.calls) == 2 and all(r["via"] == "browser" and r["outcome"] == "pass" for r in rows)


def test_fetch_with_long_text_makes_no_browser_call(m7, pid):
    mk(m7, pid, "Long", "/products/long", [C("status_ok"), C("text_has", "Solaris")])
    r = drive(m7.api, pid)
    assert m7.fb.calls == []
    assert all(row["via"] == "fetch" for rows in r.rows.values() for row in rows)


def test_post_pairs_are_never_rendered(m7, pid):
    m7.site.overrides["/thin-post"] = (200, THIN)
    pair = new_pair(m7.api, pid, "Posts", "/thin-post", [C("status_ok"), C("text_has", "Sand")], approved=True,
                    method="POST", request_body={"a": 1})
    rows = drive(m7.api, pid).rows[pair["id"]]
    assert m7.fb.calls == [] and all(r["via"] == "fetch" for r in rows)
    assert check_of(rows[0], "text_has")["passed"] is False


def test_fallback_is_skipped_when_the_page_is_an_error(m7, pid):
    pair = mk(m7, pid, "Gone", "/broken", [C("status_ok"), C("text_has", "Sand")])
    rows = drive(m7.api, pid).rows[pair["id"]]
    assert m7.fb.calls == [] and rows[0]["outcome"] == "fail"


def test_fetch_fallback_session_that_cannot_help_leaves_the_plain_answer(m7, pid, thin):
    """Documents today's behaviour: if the retry cannot render (no key, busy, login...), the plain read stands."""
    m7.fb.make = lambda call: browser.Session(device=call.device, human_reason=HUMAN["no_token"])
    for row in drive(m7.api, pid).rows[thin["id"]]:
        assert row["via"] == "fetch" and check_of(row, "status_ok")["passed"] is True
        assert check_of(row, "text_has")["passed"] is False


def test_fetch_fallback_session_with_an_error_leaves_the_plain_answer(m7, pid, thin):
    m7.fb.make = lambda call: browser.Session(device=call.device, error="The page didn't work in the browser: x")
    for row in drive(m7.api, pid).rows[thin["id"]]:
        assert row["via"] == "fetch" and check_of(row, "text_has")["passed"] is False


def test_a_pair_with_browser_checks_and_a_thin_page_uses_one_session_for_both_jobs(m7, pid):
    m7.site.overrides["/pages/app"] = (200, THIN)
    pair = mk(m7, pid, "Both", "/pages/app",
              [C("status_ok"), C("text_has", "Sand"), C("ai_vision", "Is it nice?", STEPS)])
    m7.fb.make = lambda call: browser.Session(device=call.device, status_code=200, url="u", text="Sand " * 30,
                                              shot=f"SHOT-{call.device}")
    rows = drive(m7.api, pid).rows[pair["id"]]
    assert len(m7.fb.calls) == 2  # not four
    assert all(c.want_html and c.want_shot for c in m7.fb.calls)
    assert all(r["via"] == "browser" and r["outcome"] == "pass" for r in rows)


# ---- the two pure helpers

def reply(text="x" * 400, status=200, html_="", blocked=False, error=None):
    return site.SiteReply(device="phone", url="u", status_code=status, text=text, html=html_, blocked=blocked,
                          error=error)


GET = {"method": "GET", "request_url": "/p"}


@pytest.mark.parametrize("n,expected", [(0, True), (50, True), (299, True), (300, False), (301, False)])
def test_needs_render_boundary_is_300_characters(n, expected):
    assert index._needs_render(GET, [{"rule": "text_has"}], reply("x" * n)) is expected


def test_needs_render_counts_visible_text_without_the_outer_spaces():
    assert index._needs_render(GET, [{"rule": "text_has"}], reply("  " + "x" * 290 + "  \n" * 30)) is True


@pytest.mark.parametrize("rule", ["text_has", "text_absent", "min_results", "count_equals", "ai_judge"])
def test_needs_render_for_every_fetch_text_rule(rule):
    assert index._needs_render(GET, [{"rule": "status_ok"}, {"rule": rule}], reply("hi")) is True


@pytest.mark.parametrize("rules", [["status_ok"], ["ai_vision"], ["browser_count"], ["manual"], []])
def test_needs_render_is_off_without_a_text_rule(rules):
    assert index._needs_render(GET, [{"rule": r} for r in rules], reply("hi")) is False


@pytest.mark.parametrize("bad", [reply("hi", status=404), reply("hi", status=500), reply("hi", status=301),
                                 reply("hi", blocked=True), reply("hi", error="slow"), reply("hi", status=None)])
def test_needs_render_is_off_for_errors_and_blocks(bad):
    assert index._needs_render(GET, [{"rule": "text_has"}], bad) is False


def test_needs_render_is_off_for_post():
    assert index._needs_render({**GET, "method": "POST"}, [{"rule": "text_has"}], reply("hi")) is False


@pytest.mark.parametrize("markup", ['<div id="root"></div>', '<div id="app">  \n </div>', '<div id="__next"></div>',
                                    '<div id="root" class="x"></div>'])
def test_needs_render_sees_an_empty_js_shell_even_with_long_text(markup):
    assert index._needs_render(GET, [{"rule": "text_has"}], reply(html_=markup)) is True


def test_needs_render_sees_the_enable_javascript_message_in_any_case():
    assert index._needs_render(GET, [{"rule": "text_has"}], reply("x" * 400 + " Please Enable JavaScript to continue")) is True


def test_needs_render_is_off_for_a_filled_root_div():
    assert index._needs_render(GET, [{"rule": "text_has"}], reply(html_='<div id="root"><p>hello</p></div>')) is False


def test_session_steps_prefers_the_first_browser_check_with_steps():
    checks = [{"rule": "status_ok"}, {"rule": "ai_vision", "steps": None},
              {"rule": "ai_vision", "steps": [{"goto": "/a"}]}, {"rule": "browser_count", "steps": [{"goto": "/b"}]}]
    assert index._session_steps(GET, checks) == [{"goto": "/a"}]


def test_session_steps_default_is_the_pairs_page_or_home_for_post():
    assert index._session_steps({"method": "GET", "request_url": "/p?q=1"}, [{"rule": "ai_vision"}]) == [{"goto": "/p?q=1"}]
    assert index._session_steps({"method": "GET", "request_url": None}, []) == [{"goto": "/"}]
    assert index._session_steps({"method": "POST", "request_url": "/cart/add.js"}, []) == [{"goto": "/"}]


# ================================================================ 7 · blocked site

def test_blocked_fetch_is_cant_test_and_never_opens_the_browser(m7, pid):
    pair = mk(m7, pid, "Blocked", "/blocked", [C("status_ok"), C("ai_vision", "Is it nice?", STEPS),
                                              C("browser_count", "item_count=1")])
    r = drive(m7.api, pid)
    assert m7.fb.calls == [] and m7.fv.calls == []
    for row in r.rows[pair["id"]]:
        assert row["outcome"] == "cant_test" and row["via"] == "fetch" and row["why"] == BLOCKED_WHY
        assert {c["why"] for c in row["checks"]} == {BLOCKED_WHY}
        assert row["human_reason"] == ""


def test_blocked_thin_text_pair_is_not_rendered_either(m7, pid):
    mk(m7, pid, "Blocked", "/blocked", [C("status_ok"), C("text_has", "Sand")])
    drive(m7.api, pid)
    assert m7.fb.calls == []


def test_one_pair_blocked_and_the_next_one_still_uses_its_sessions(m7, pid):
    mk(m7, pid, "Blocked", "/blocked", [C("ai_vision", "Is it nice?", STEPS)])
    mk(m7, pid, "Fine", "/products/solaris", [C("ai_vision", "Is it nice?", STEPS)])
    drive(m7.api, pid)
    assert [c.start_path for c in m7.fb.calls] == ["/products/solaris"] * 2


# ================================================================ 8 · a click that cannot be done

def test_session_error_fails_the_browser_checks_with_that_message(m7, pid):
    msg = 'We couldn\'t find "Sand" to click on the page.'
    pair = mk(m7, pid, "Picks Sand", "/products/solaris",
              [C("status_ok"), C("ai_vision", "Is Sand selected?", STEPS), C("browser_count", "item_count=1")])
    m7.fb.make = lambda call: browser.Session(device=call.device, error=msg)
    r = drive(m7.api, pid)
    assert m7.fv.calls == []
    for row in r.rows[pair["id"]]:
        assert row["via"] == "browser" and row["outcome"] == "fail" and row["human_reason"] == ""
        for rule in ("ai_vision", "browser_count"):
            c = check_of(row, rule)
            assert c["passed"] is False and c["why"] == msg
        assert row["why"] == msg
        assert check_of(row, "status_ok")["passed"] is True
    assert r.done["run"]["passed"] == 0
    # the failure gets a diagnosis like any other
    assert ok(m7.api.get(f"/api/runs/{r.id}"))["points"]


def test_browser_count_with_no_cart_after_the_clicks_fails_in_plain_words(m7, pid):
    pair = mk(m7, pid, "Cart", "/products/solaris", [C("browser_count", "item_count=1", STEPS)])
    m7.fb.make = lambda call: browser.Session(device=call.device, status_code=200, url="u", text="x", cart=None)
    for row in drive(m7.api, pid).rows[pair["id"]]:
        c = check_of(row, "browser_count")
        assert c["passed"] is False and c["why"] == "We couldn't read the cart after the clicks."
        assert row["via"] == "browser"


def test_browser_count_with_a_malformed_expected_is_a_failure_not_a_crash(m7, pid):
    pair = mk(m7, pid, "Cart", "/products/solaris", [C("browser_count", "one item", STEPS)])
    row = drive(m7.api, pid).rows[pair["id"]][0]
    assert check_of(row, "browser_count")["passed"] is False and row["outcome"] == "fail"


# ================================================================ 9 · doors 6 and 7 take and clean steps

def body(checks, **over):
    return {"user_does": "Picks Sand", "good_result": "Sand shows", "request_url": "/products/solaris",
            "method": "GET", "checks": checks, **over}


def test_door_6_saves_cleaned_steps_and_returns_them_on_the_checks(m7, pid):
    raw = [{"goto": "/products/solaris"}, {"click": "Sand"}, {"click": "css=button[name=add]", "optional": True},
           {"wait": 99}, {"scroll": "bottom"}]
    pair = ok(m7.api.post(f"/api/projects/{pid}/pairs", body([
        C("status_ok"), C("ai_vision", "Is Sand selected?", raw), C("browser_count", "item_count=1", [{"goto": "/"}])])), 201)["pair"]
    by_rule = {c["rule"]: c for c in pair["checks"]}
    assert by_rule["ai_vision"]["steps"] == [{"goto": "/products/solaris"}, {"click": "text=Sand"},
                                             {"click": "css=button[name=add]", "optional": True},
                                             {"wait": 5.0}, {"scroll": "bottom"}]
    assert by_rule["browser_count"]["steps"] == [{"goto": "/"}]
    assert by_rule["status_ok"]["steps"] is None
    assert by_rule["ai_vision"]["decided_by"] == "ai" and by_rule["browser_count"]["decided_by"] == "code"
    saved = ok(m7.api.get(f"/api/projects/{pid}"))["pairs"][0]["checks"]
    assert {c["rule"]: c["steps"] for c in saved} == {c["rule"]: c["steps"] for c in pair["checks"]}


def test_steps_on_a_fetch_check_are_dropped(m7, pid):
    pair = ok(m7.api.post(f"/api/projects/{pid}/pairs", body([C("text_has", "Sand", [{"click": "Buy it now"}])])), 201)["pair"]
    assert pair["checks"][0]["steps"] is None


def test_browser_check_without_steps_saves_none(m7, pid):
    pair = ok(m7.api.post(f"/api/projects/{pid}/pairs", body([C("ai_vision", "Looks nice?")])), 201)["pair"]
    assert pair["checks"][0]["steps"] is None
    pair = ok(m7.api.post(f"/api/projects/{pid}/pairs", body([C("ai_vision", "Looks nice?", [])])), 201)["pair"]
    assert pair["checks"][0]["steps"] is None


def test_door_7_replaces_checks_with_steps(m7, pid):
    pair = new_pair(m7.api, pid, "P", "/products/solaris", [C("status_ok")])
    out = ok(m7.api.patch(f"/api/pairs/{pair['id']}", {"checks": [C("ai_vision", "Nice?", [{"click": "Sand"}])]}))["pair"]
    assert [c["steps"] for c in out["checks"]] == [[{"click": "text=Sand"}]]


@pytest.mark.parametrize("label", ["Buy it now", "Pay now", "Log in", "Place order", "Sign up"])
def test_door_6_and_7_reject_forbidden_clicks_with_a_plain_message(m7, pid, label):
    steps = [{"goto": "/products/solaris"}, {"click": label}]
    msg = err(m7.api.post(f"/api/projects/{pid}/pairs", body([C("ai_vision", "Nice?", steps)])), 400)
    assert msg == f'We never click "{label}": it could pay, order, log in or sign up.'
    pair = new_pair(m7.api, pid, "P", "/products/solaris", [C("status_ok")])
    assert err(m7.api.patch(f"/api/pairs/{pair['id']}", {"checks": [C("browser_count", "item_count=1", steps)]}), 400) == msg
    assert ok(m7.api.get(f"/api/projects/{pid}"))["pairs"][0]["checks"][0]["rule"] == "status_ok"  # nothing saved


@pytest.mark.parametrize("goto", ["products/solaris", "https://evil.example/x", "//evil.example", ""])
def test_door_6_rejects_a_goto_without_a_leading_slash(m7, pid, goto):
    msg = err(m7.api.post(f"/api/projects/{pid}/pairs", body([C("ai_vision", "Nice?", [{"goto": goto}])])), 400)
    assert "must start with /" in msg
    assert ok(m7.api.get(f"/api/projects/{pid}"))["pairs"] == []


def test_door_6_rejects_too_many_steps_and_unknown_actions(m7, pid):
    err(m7.api.post(f"/api/projects/{pid}/pairs", body([C("ai_vision", "Nice?", [{"goto": "/a"}] * 9)])), 400)
    err(m7.api.post(f"/api/projects/{pid}/pairs", body([C("ai_vision", "Nice?", [{"hover": "x"}])])), 400)
    err(m7.api.post(f"/api/projects/{pid}/pairs", body([C("ai_vision", "Nice?", "click Sand")])), 400)


@pytest.mark.parametrize("rule", ["ai_vision", "browser_count"])
@pytest.mark.parametrize("expected", [None, "", "   "])
def test_door_6_needs_an_expected_for_browser_checks(m7, pid, rule, expected):
    msg = err(m7.api.post(f"/api/projects/{pid}/pairs", body([C(rule, expected, STEPS)])), 400)
    assert msg == "One of the checks needs something to look for."


def test_door_6_accepts_browser_check_beside_manual_and_ai_judge(m7, pid):
    pair = ok(m7.api.post(f"/api/projects/{pid}/pairs", body([
        C("status_ok"), C("ai_judge", "Is it there?"), C("manual", "Looks friendly?"), C("ai_vision", "Nice?", STEPS)])), 201)["pair"]
    assert [c["rule"] for c in pair["checks"]] == ["status_ok", "ai_judge", "manual", "ai_vision"]


def test_door_6_answers_400_for_a_scroll_that_is_not_a_number(m7, pid):
    err(m7.api.post(f"/api/projects/{pid}/pairs", body([C("ai_vision", "Nice?", [{"scroll": [1, 2]}])])), 400)


def test_door_6_rejects_a_click_with_nothing_after_the_prefix(m7, pid):
    err(m7.api.post(f"/api/projects/{pid}/pairs", body([C("ai_vision", "Nice?", [{"click": "text="}])])), 400)


# ================================================================ 10 · the AI draft never says "manual"

def tidy_with(m7, monkeypatch, ai_draft, kind=None, rough="Open the menu on a phone"):
    monkeypatch.setattr(groq, "tidy_pair", REAL_TIDY)
    monkeypatch.setattr(groq, "change_to_pair", REAL_CHANGE)
    monkeypatch.setattr(groq, "chat_json", lambda system, user, max_tokens=1500, timeout=25: ai_draft)
    payload = {"rough_text": rough, "site_url": SITE_URL, **({"kind": kind} if kind else {})}
    return ok(m7.api.post("/api/pairs/tidy", payload))["pair"]


def ai(checks, **over):
    return {"user_does": "Opens the menu", "good_result": "The menu opens", "request_url": "/collections/all",
            "method": "GET", "request_body": None, "checks": checks, **over}


def test_tidy_turns_a_manual_check_into_ai_vision_with_a_goto_step(m7, monkeypatch):
    pair = tidy_with(m7, monkeypatch, ai([{"decided_by": "human", "rule": "manual", "expected": "Is the menu open?"}]))
    rules = [c["rule"] for c in pair["checks"]]
    assert "manual" not in rules and "human" not in {c["decided_by"] for c in pair["checks"]}
    vis = next(c for c in pair["checks"] if c["rule"] == "ai_vision")
    assert vis == {"decided_by": "ai", "rule": "ai_vision", "expected": "Is the menu open?",
                   "steps": [{"goto": "/collections/all"}]}
    assert pair["checks"][0]["rule"] == "status_ok"  # the always-present status check is added first


def test_tidy_keeps_good_steps_and_replaces_bad_ones(m7, monkeypatch):
    good = [{"goto": "/"}, {"click": "css=summary[aria-label=Menu]", "optional": True}]
    bad = [{"goto": "https://evil.example/"}]
    forbidden = [{"goto": "/"}, {"click": "Buy it now"}]
    pair = tidy_with(m7, monkeypatch, ai([
        {"rule": "ai_vision", "expected": "Q1?", "steps": good},
        {"rule": "ai_vision", "expected": "Q2?", "steps": bad},
        {"rule": "browser_count", "expected": "item_count=1", "steps": forbidden},
        {"rule": "manual", "expected": "Q3?", "steps": forbidden}]))
    steps = {c["expected"]: c["steps"] for c in pair["checks"] if c["steps"]}
    assert steps["Q1?"] == good
    assert steps["Q2?"] == [{"goto": "/collections/all"}]
    assert steps["item_count=1"] == [{"goto": "/collections/all"}]
    assert steps["Q3?"] == [{"goto": "/collections/all"}]
    assert not any(c["rule"] == "manual" for c in pair["checks"])


def test_tidy_manual_without_a_question_is_dropped(m7, monkeypatch):
    pair = tidy_with(m7, monkeypatch, ai([{"rule": "manual", "expected": None}, {"rule": "manual", "expected": "  "}]))
    assert [c["rule"] for c in pair["checks"]] == ["status_ok"]


def test_tidy_manual_on_a_post_pair_gets_the_home_page_step(m7, monkeypatch):
    pair = tidy_with(m7, monkeypatch, ai([{"rule": "manual", "expected": "Is the cart open?"}], method="POST",
                                          request_url="/cart/add.js", request_body={"items": []}))
    assert next(c for c in pair["checks"] if c["rule"] == "ai_vision")["steps"] == [{"goto": "/"}]


def test_tidy_change_kind_also_never_returns_manual(m7, monkeypatch):
    pair = tidy_with(m7, monkeypatch, ai([{"rule": "MANUAL", "expected": "Is the banner red?"}],
                                         request_url="/pages/shipping"), kind="change", rough="I made the banner red")
    vis = next(c for c in pair["checks"] if c["rule"] == "ai_vision")
    assert vis["steps"] == [{"goto": "/pages/shipping"}] and vis["decided_by"] == "ai"


def test_tidy_suggestions_never_return_manual(m7, pid, monkeypatch):
    monkeypatch.setattr(groq, "suggest_pairs", REAL_SUGGEST)
    monkeypatch.setattr(site, "fetch_home_text", lambda url: "Welcome to the shop")
    monkeypatch.setattr(groq, "chat_json", lambda system, user, max_tokens=1500, timeout=25: {
        "pairs": [ai([{"rule": "manual", "expected": "Is the hero image sharp?"}])]})
    pairs = ok(m7.api.post(f"/api/projects/{pid}/suggestions"))["pairs"]
    assert [c["rule"] for c in pairs[0]["checks"]] == ["status_ok", "ai_vision"]
    assert pairs[0]["checks"][1]["steps"] == [{"goto": "/collections/all"}]


def test_a_tidy_draft_can_be_saved_through_door_6_as_is(m7, pid, monkeypatch):
    draft_ = tidy_with(m7, monkeypatch, ai([{"rule": "manual", "expected": "Is the menu open?"}]))
    saved = ok(m7.api.post(f"/api/projects/{pid}/pairs", {**draft_, "approved": True}), 201)["pair"]
    assert [c["rule"] for c in saved["checks"]] == ["status_ok", "ai_vision"]
    assert saved["checks"][1]["steps"] == [{"goto": "/collections/all"}]


# ================================================================ 11 · health

def test_health_reports_whether_a_browser_key_exists_and_never_the_key(api, monkeypatch):
    secret = "bl-SECRET-VALUE-123"
    assert ok(api.get("/api/health", tok=None)) == {"ok": True, "browser": False}
    monkeypatch.setenv("BROWSERLESS_TOKEN", secret)
    resp = api.get("/api/health", tok=None)
    assert resp.json() == {"ok": True, "browser": True} and secret not in resp.text
    monkeypatch.delenv("BROWSERLESS_TOKEN")
    assert ok(api.get("/api/health", tok=None)) == {"ok": True, "browser": False}


def test_health_sees_any_browserless_named_variable(api, monkeypatch):
    monkeypatch.setenv("MY_BROWSERLESS_KEY", "k-123")
    resp = api.get("/api/health", tok=None)
    assert resp.json()["browser"] is True and "k-123" not in resp.text


@pytest.mark.parametrize("value", ["", "   "])
def test_health_blank_key_is_not_configured(api, monkeypatch, value):
    monkeypatch.setenv("BROWSERLESS_TOKEN", value)
    assert ok(api.get("/api/health", tok=None))["browser"] is False


def test_health_needs_no_login_and_has_exactly_two_fields(api, monkeypatch):
    monkeypatch.setenv("BROWSERLESS_TOKEN", "x")
    assert set(ok(api.get("/api/health", tok=None))) == {"ok", "browser"}


# ================================================================ 12 · re-run of changed pairs

def test_rerun_of_one_browser_pair_opens_two_sessions_and_leaves_run_1_alone(m7, pid):
    a = mk(m7, pid, "Pair A", "/products/a", [C("status_ok"), C("ai_vision", "Is A nice?", STEPS)])
    b = mk(m7, pid, "Pair B", "/products/b", [C("status_ok"), C("browser_count", "item_count=1", STEPS)])
    r1 = drive(m7.api, pid)
    assert len(m7.fb.calls) == 4
    run1_before = ok(m7.api.get(f"/api/runs/{r1.id}"))
    m7.fb.calls.clear()
    m7.fv.calls.clear()
    m7.fb.make = lambda call: browser.Session(device=call.device, status_code=200, url="u", text="x", cart=CART_5,
                                              shot="SHOT-new")
    r2 = drive(m7.api, pid, {"kind": "changed", "pair_ids": [b["id"]]})
    assert m7.fb.devices() == ["phone", "laptop"] and {c.start_path for c in m7.fb.calls} == {"/products/b"}
    assert m7.fv.calls == []  # pair B has no vision check
    assert r2.order == [b["id"]]
    assert all(row["outcome"] == "fail" for row in r2.rows[b["id"]])
    run1_after = ok(m7.api.get(f"/api/runs/{r1.id}"))
    assert run1_after == run1_before
    assert all(row["outcome"] == "pass" for row in run1_after["rows"])
    cmp_ = ok(m7.api.get(f"/api/runs/{r2.id}/compare"))
    assert {x["verdict"] for x in cmp_["rows"]} == {"BROKE"}
    assert a["id"] not in {x["pair_id"] for x in cmp_["rows"]}


def test_rerun_counts_its_own_cap_from_zero(m7, pid):
    vision_pairs(m7, pid, 7)
    drive(m7.api, pid)
    pairs = ok(m7.api.get(f"/api/projects/{pid}"))["pairs"]
    m7.fb.calls.clear()
    r2 = drive(m7.api, pid, {"kind": "changed", "pair_ids": [pairs[6]["id"]]})  # the one capped in run 1
    assert len(m7.fb.calls) == 2
    assert all(row["via"] == "browser" for row in r2.rows[pairs[6]["id"]])


# ================================================================ 13 · reading results back

def test_rows_carry_the_checks_steps(m7, pid):
    pair = mk(m7, pid, "Look", "/products/solaris", [C("status_ok"), C("ai_vision", "Nice?", STEPS)])
    row = drive(m7.api, pid).rows[pair["id"]][0]
    assert check_of(row, "status_ok")["steps"] is None
    assert check_of(row, "ai_vision")["steps"] == [{"goto": "/products/solaris"}, {"click": "text=Sand"}]
    again = [x for x in ok(m7.api.get(f"/api/runs/{row['run_id']}"))["rows"] if x["result_id"] == row["result_id"]][0]
    assert check_of(again, "ai_vision")["steps"] == check_of(row, "ai_vision")["steps"]


def test_door_13_returns_the_same_check_result_shape_as_the_rows(m7, pid):
    pair = mk(m7, pid, "Look", "/products/solaris", [C("status_ok"), C("ai_vision", "Nice?", STEPS)])
    m7.fb.make = lambda call: browser.Session(device=call.device, human_reason=HUMAN["payment"])
    row = drive(m7.api, pid).rows[pair["id"]][0]
    target = check_of(row, "ai_vision")
    answered = ok(m7.api.patch(f"/api/result-checks/{target['id']}", {"passed": True}))["check"]
    assert set(answered) == set(target)
    assert answered["steps"] == target["steps"]


def test_via_and_human_reason_are_on_every_row_of_a_mixed_run(m7, pid):
    plain = mk(m7, pid, "Plain", "/products/a", [C("status_ok")])
    look = mk(m7, pid, "Look", "/products/b", [C("status_ok"), C("ai_vision", "Nice?", STEPS)])
    pay = mk(m7, pid, "Pay", "/products/c", [C("status_ok"), C("browser_count", "item_count=1", STEPS)])
    manual = mk(m7, pid, "Manual", "/products/d", [C("status_ok"), C("manual", "Friendly?")])
    m7.fb.make = lambda call: (browser.Session(device=call.device, human_reason=HUMAN["payment"])
                               if call.start_path == "/products/c" else FakeBrowser.default(call))
    r = drive(m7.api, pid)
    rows = ok(m7.api.get(f"/api/runs/{r.id}"))["rows"]
    got = {(x["pair_id"], x["device"]): (x["via"], x["human_reason"]) for x in rows}
    for d in ("phone", "laptop"):
        assert got[(plain["id"], d)] == ("fetch", "")
        assert got[(look["id"], d)] == ("browser", "")
        assert got[(pay["id"], d)] == ("human", HUMAN["payment"])
        assert got[(manual["id"], d)] == ("human", "")  # a manual check is a person too, but not a browser reason


def test_finish_explains_a_failed_browser_result(m7, pid):
    pair = mk(m7, pid, "Cart", "/products/solaris", [C("status_ok"), C("browser_count", "item_count=1", STEPS)])
    m7.fb.make = lambda call: browser.Session(device=call.device, status_code=200, url="u", text="x", cart=CART_5)
    r = drive(m7.api, pid)
    assert r.done["run"]["passed"] == 0 and r.done["run"]["total"] == 2
    assert [p["rank"] for p in r.done["points"]] == [1, 2] and pair["id"] == r.done["points"][0]["pair_id"]


def test_the_run_finishes_when_the_browser_module_raises_nothing_but_returns_odd_sessions(m7, pid):
    pair = mk(m7, pid, "Odd", "/products/solaris", [C("status_ok"), C("ai_vision", "Nice?", STEPS),
                                                     C("browser_count", "item_count=1")])
    m7.fb.make = lambda call: browser.Session(device=call.device)  # nothing set at all: no cart, no shot, no reason
    r = drive(m7.api, pid)
    for row in r.rows[pair["id"]]:
        assert check_of(row, "browser_count")["passed"] is False
        assert check_of(row, "ai_vision")["passed"] is None  # no picture: unsure, a person looks
    assert r.done["run"]["total"] == 2


def test_each_browser_session_writes_one_plain_log_line_without_the_token(m7, pid, lamp, capsys, monkeypatch):
    monkeypatch.setenv("BROWSERLESS_TOKEN", "tok-secret-123")
    drive(m7.api, pid)
    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("[browser]")]
    assert len(lines) == 2
    assert lines[0].startswith("[browser] pair #") and " phone: worked · browser opened yes" in lines[0]
    assert " laptop: worked" in lines[1] and "cart 1 item(s)" in lines[1] and "screenshot yes" in lines[1]
    assert all("tok-secret" not in l and "SHOT-" not in l for l in lines)
