"""Unit tests of api/_lib/browser.py (the real-browser client). No network: requests.post is mocked and
time.sleep is patched so the 5 s "busy" wait never really happens.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from unittest.mock import MagicMock

import pytest
import requests

from api._lib import browser, site

SITE = "https://shop.example.com"
KEY = "tok-SECRET-123"


# ---------------------------------------------------------------- helpers

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No Browserless variable leaks in from the machine; each test sets what it needs."""
    import os
    for name in list(os.environ):
        if "BROWSERLESS" in name.upper():
            monkeypatch.delenv(name, raising=False)


def resp(status=200, data=None, text=None, bare=False, bad_json=False):
    """A fake requests.Response. `data` is the function's result, wrapped like Browserless wraps it."""
    r = MagicMock()
    r.status_code = status
    body = data if (bare and data is not None) else ({"data": data, "type": "application/json"} if data is not None else {})
    r.text = text if text is not None else ("not json" if bad_json else json.dumps(body))
    if bad_json:
        r.json.side_effect = ValueError("not json")
    else:
        r.json.return_value = body
    return r


class Net:
    """Scripted requests.post: each call pops the next queued response (or raises the queued exception)."""

    def __init__(self):
        self.queue: list = []
        self.posts: list[tuple] = []
        self.sleeps: list[float] = []

    def post(self, url, **kw):
        self.posts.append((url, kw))
        assert self.queue, "unexpected extra HTTP call"
        item = self.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    @property
    def last(self) -> dict:
        return self.posts[-1][1]


@pytest.fixture
def net(monkeypatch):
    n = Net()
    monkeypatch.setattr(requests, "post", n.post)
    monkeypatch.setattr(browser.time, "sleep", lambda s: n.sleeps.append(s))
    monkeypatch.setenv("BROWSERLESS_TOKEN", KEY)
    return n


def go(device="phone", steps=None, **kw):
    args = dict(site_url=SITE, start_path="/products/solaris", steps=steps, device=device,
                want_shot=False, want_cart=False)
    args.update(kw)
    return browser.run(**args)


OK_DATA = {"status": 200, "url": SITE + "/products/solaris", "title": "Solaris", "text": "Solaris lamp",
           "html": "<html></html>", "cart": None, "shot": None, "human_reason": None, "error": None,
           "out_of_time": False, "notes": ["opened /products/solaris"]}


# ================================================================ token / configured

def test_token_prefers_browserless_token(monkeypatch):
    monkeypatch.setenv("BROWSERLESS_TOKEN", "  main  ")
    monkeypatch.setenv("MY_BROWSERLESS_KEY", "other")
    assert browser.token() == "main"
    assert browser.configured() is True


def test_token_falls_back_to_any_browserless_named_variable(monkeypatch):
    monkeypatch.setenv("BROWSERLESS_API_KEY", " abc ")
    assert browser.token() == "abc"


def test_token_name_match_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("my_browserless_key", "lower")
    assert browser.token() == "lower"


def test_empty_browserless_token_does_not_hide_a_second_variable(monkeypatch):
    monkeypatch.setenv("BROWSERLESS_TOKEN", "   ")
    monkeypatch.setenv("BROWSERLESS_KEY", "second")
    assert browser.token() == "second"


def test_token_is_empty_when_nothing_is_set(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "not-it")
    monkeypatch.setenv("BROWSERLESS_EMPTY", "  ")
    assert browser.token() == ""
    assert browser.configured() is False


# ================================================================ run(): no call at all

def test_no_token_is_human_and_makes_no_http_call(net):
    import os
    os.environ.pop("BROWSERLESS_TOKEN")
    s = go()
    assert s.human_reason == browser.HUMAN["no_token"]
    assert net.posts == []


@pytest.mark.parametrize("budget", [0, 14.9, 14.999, -3])
def test_too_little_time_is_human_and_makes_no_http_call(net, budget):
    s = go(budget_s=budget)
    assert s.human_reason == browser.HUMAN["time"]
    assert net.posts == []


def test_budget_of_exactly_15_seconds_is_enough(net):
    net.queue = [resp(data=OK_DATA)]
    s = go(budget_s=15)
    assert s.human_reason is None and len(net.posts) == 1
    assert net.last["params"]["timeout"] == 15_000
    assert net.last["json"]["context"]["budgetMs"] == 7_000


def test_a_big_budget_is_capped_at_45_seconds(net):
    net.queue = [resp(data=OK_DATA)]
    go(budget_s=500)
    assert net.last["params"]["timeout"] == 45_000 == browser.SESSION_MS
    assert net.last["json"]["context"]["budgetMs"] == 37_000
    assert net.last["timeout"] == pytest.approx(53)  # our own HTTP timeout is a little longer than the session


# ================================================================ run(): the request

@pytest.mark.parametrize("device,width,height,mobile", [("phone", 390, 844, True), ("laptop", 1440, 900, False)])
def test_request_shape(net, device, width, height, mobile):
    net.queue = [resp(data=OK_DATA)]
    steps = [{"goto": "/products/solaris"}, {"click": "text=Sand"}]
    go(device=device, steps=steps, want_shot=True, want_cart=True, want_html=True)
    url, kw = net.posts[0]
    assert url == browser.FUNCTION_URL == "https://production-sfo.browserless.io/function"
    assert kw["params"] == {"token": KEY, "timeout": 45_000, "blockAds": "true"}
    assert kw["params"]["timeout"] <= 45_000
    body = kw["json"]
    assert set(body) == {"code", "context"}
    assert body["code"] == browser._JS and "export default async function" in body["code"]
    ctx = body["context"]
    assert ctx["viewport"]["width"] == width and ctx["viewport"]["height"] == height
    assert ctx["viewport"].get("isMobile", False) is mobile
    assert ctx["ua"] == site.UA[device]
    assert ctx["steps"] == steps and ctx["start"] == "/products/solaris" and ctx["base"] == SITE
    assert ctx["wantShot"] is True and ctx["wantCart"] is True and ctx["wantHtml"] is True
    assert ctx["forbidden"] == browser.FORBIDDEN


def test_request_flags_default_to_off_and_base_loses_the_trailing_slash(net):
    net.queue = [resp(data=OK_DATA)]
    browser.run(SITE + "/", "", None, "laptop", want_shot=False, want_cart=False)
    ctx = net.last["json"]["context"]
    assert (ctx["wantShot"], ctx["wantCart"], ctx["wantHtml"]) == (False, False, False)
    assert ctx["base"] == SITE and ctx["start"] == "/" and ctx["steps"] == []


def test_phone_and_laptop_user_agents_differ(net):
    net.queue = [resp(data=OK_DATA), resp(data=OK_DATA)]
    go("phone")
    go("laptop")
    uas = [p[1]["json"]["context"]["ua"] for p in net.posts]
    assert uas[0] != uas[1] and "iPhone" in uas[0] and "Macintosh" in uas[1]


# ================================================================ run(): failures become plain reasons

def test_401_is_bad_token(net):
    net.queue = [resp(401, text="Unauthorized")]
    assert go().human_reason == browser.HUMAN["bad_token"]
    assert len(net.posts) == 1 and net.sleeps == []


def test_403_is_bad_token(net):
    net.queue = [resp(403, text="Forbidden")]
    assert go().human_reason == browser.HUMAN["bad_token"]


def test_429_twice_is_busy_after_exactly_two_posts_and_one_five_second_wait(net):
    net.queue = [resp(429, text="Too many"), resp(429, text="Too many")]
    s = go()
    assert s.human_reason == browser.HUMAN["busy"]
    assert len(net.posts) == 2
    assert net.sleeps == [5]


def test_429_then_200_succeeds(net):
    net.queue = [resp(429, text="Too many"), resp(data=OK_DATA)]
    s = go()
    assert s.human_reason is None and s.error is None and s.text == "Solaris lamp"
    assert len(net.posts) == 2 and net.sleeps == [5]


def test_429_then_timeout_is_slow(net):
    net.queue = [resp(429), requests.Timeout()]
    assert go().human_reason == browser.HUMAN["slow"]
    assert len(net.posts) == 2


@pytest.mark.parametrize("text", ["", "Payment required", "You have no units left", "Monthly quota exceeded"])
def test_402_is_units(net, text):
    net.queue = [resp(402, text=text)]
    assert go().human_reason == browser.HUMAN["units"]


@pytest.mark.parametrize("status,text", [(400, "Out of units for this month"), (500, "quota used"),
                                         (403, "units exhausted"), (401, "Quota reached")])
def test_body_mentioning_units_or_quota_is_units(net, status, text):
    net.queue = [resp(status, text=text)]
    assert go().human_reason == browser.HUMAN["units"]


@pytest.mark.parametrize("status", [500, 502, 503, 504, 400, 404])
def test_5xx_and_other_errors_are_down_without_retry(net, status):
    net.queue = [resp(status, text="Internal error")]
    assert go().human_reason == browser.HUMAN["down"]
    assert len(net.posts) == 1 and net.sleeps == []


def test_408_is_slow(net):
    net.queue = [resp(408, text="Request timeout")]
    assert go().human_reason == browser.HUMAN["slow"]


def test_timeout_is_slow_and_not_retried(net):
    net.queue = [requests.Timeout()]
    assert go().human_reason == browser.HUMAN["slow"]
    assert len(net.posts) == 1


def test_read_timeout_is_slow(net):
    net.queue = [requests.exceptions.ReadTimeout()]
    assert go().human_reason == browser.HUMAN["slow"]


@pytest.mark.parametrize("exc", [requests.ConnectionError("no route"), requests.exceptions.SSLError("tls")])
def test_connection_trouble_is_down(net, exc):
    net.queue = [exc]
    assert go().human_reason == browser.HUMAN["down"]


def test_200_that_is_not_json_is_down(net):
    net.queue = [resp(200, bad_json=True)]
    assert go().human_reason == browser.HUMAN["down"]


def test_run_never_raises_on_odd_bodies(net):
    for body in ([1, 2], "text", None, {}, {"data": {"cart": "nope", "notes": None}}):
        r = MagicMock()
        r.status_code = 200
        r.text = "x"
        r.json.return_value = body
        net.queue = [r]
        s = go()
        assert isinstance(s, browser.Session)


@pytest.mark.parametrize("body", [{"data": None}, {"data": "oops"}, {"data": [1]}])
def test_run_never_raises_when_data_is_not_an_object(net, body):
    r = MagicMock()
    r.status_code = 200
    r.text = "x"
    r.json.return_value = body
    net.queue = [r]
    assert isinstance(go(), browser.Session)


# ================================================================ run(): what a 200 can say

@pytest.mark.parametrize("reason", ["payment", "login", "captcha"])
def test_human_reason_from_the_page_maps_to_the_right_text(net, reason):
    net.queue = [resp(data={**OK_DATA, "human_reason": reason})]
    s = go()
    assert s.human_reason == browser.HUMAN[reason]
    assert s.error is None


def test_the_three_page_reasons_say_what_they_are():
    assert "Payment" in browser.HUMAN["payment"] and "Login" in browser.HUMAN["login"]
    assert "captcha" in browser.HUMAN["captcha"].lower()
    assert browser.HUMAN["payment"] == "Payment page, a person needs to check this"
    assert browser.HUMAN["cap"] == "Browser limit for this run reached"


def test_unknown_page_reason_is_down(net):
    net.queue = [resp(data={**OK_DATA, "human_reason": "weird"})]
    assert go().human_reason == browser.HUMAN["down"]


def test_forbidden_click_reason_names_the_button(net):
    net.queue = [resp(data={**OK_DATA, "human_reason": "forbidden:Buy it now"})]
    s = go()
    assert "Buy it now" in s.human_reason and "a person needs to check this" in s.human_reason
    assert s.error is None


def test_data_error_sets_error_not_human_reason(net):
    net.queue = [resp(data={**OK_DATA, "error": 'We couldn\'t find "Sand" to click on the page.'})]
    s = go()
    assert s.error == 'We couldn\'t find "Sand" to click on the page.'
    assert s.human_reason is None


def test_long_error_is_cut_to_300(net):
    net.queue = [resp(data={**OK_DATA, "error": "x" * 900})]
    assert len(go().error) == 300


def test_out_of_time_is_slow(net):
    net.queue = [resp(data={**OK_DATA, "out_of_time": True})]
    s = go()
    assert s.human_reason == browser.HUMAN["slow"] and s.error is None


def test_page_reason_beats_out_of_time_and_error(net):
    net.queue = [resp(data={**OK_DATA, "human_reason": "login", "out_of_time": True, "error": "boom"})]
    s = go()
    assert s.human_reason == browser.HUMAN["login"] and s.error is None


def test_out_of_time_beats_error(net):
    net.queue = [resp(data={**OK_DATA, "out_of_time": True, "error": "boom"})]
    s = go()
    assert s.human_reason == browser.HUMAN["slow"] and s.error is None


def test_a_good_answer_fills_the_session(net):
    cart = {"item_count": 1, "currency": "EUR", "total_price": 7900,
            "items": [{"product_title": "Solaris", "quantity": 1, "final_price": 7900}]}
    data = {**OK_DATA, "cart": cart, "shot": "QUJD", "notes": [f"n{i}" for i in range(20)]}
    net.queue = [resp(data=data)]
    s = go("laptop", want_shot=True, want_cart=True)
    assert (s.device, s.status_code, s.url, s.text, s.html) == ("laptop", 200, SITE + "/products/solaris",
                                                                  "Solaris lamp", "<html></html>")
    assert s.cart == cart and s.shot == "QUJD" and len(s.notes) == 10
    assert s.human_reason is None and s.error is None


def test_a_bare_dict_without_the_data_wrapper_also_works(net):
    net.queue = [resp(data=OK_DATA, bare=True)]
    s = go()
    assert s.text == "Solaris lamp" and s.status_code == 200


def test_cart_that_is_not_a_dict_is_dropped_and_shot_must_be_text(net):
    net.queue = [resp(data={**OK_DATA, "cart": [1], "shot": 5})]
    s = go()
    assert s.cart is None and s.shot is None


# ================================================================ secrets

def test_token_never_appears_in_the_session_or_its_note(net):
    outcomes = [resp(data=OK_DATA), resp(401, text="bad"), resp(402), resp(500), requests.Timeout(),
                resp(data={**OK_DATA, "human_reason": "payment"}), resp(data={**OK_DATA, "error": "boom"})]
    for item in outcomes:
        net.queue = [item]
        s = go()
        assert KEY not in repr(s)
        assert KEY not in s.note()
        assert KEY not in json.dumps(s.__dict__, default=str)


def test_token_is_only_in_the_query_params_not_the_body(net):
    net.queue = [resp(data=OK_DATA)]
    go()
    assert KEY not in json.dumps(net.last["json"])
    assert net.last["params"]["token"] == KEY


# ================================================================ Session

def test_note_starts_with_real_browser_and_is_short():
    assert browser.Session(device="phone").note() == ""  # no browser ran: never claim one
    assert browser.Session(device="phone", ran=True).note() == "Real browser"
    cart = {"item_count": 1, "currency": "EUR", "total_price": 7900,
            "items": [{"product_title": "Solaris", "quantity": 1, "final_price": 7900}]}
    s = browser.Session(ran=True, device="phone", notes=["opened /", "clicked Sand"], cart=cart)
    note = s.note()
    assert note.startswith("Real browser") and "clicked Sand" in note and "Cart has 1 item" in note


def test_note_is_never_over_500_characters():
    s = browser.Session(ran=True, device="laptop", notes=["n" * 300 for _ in range(10)],
                        cart={"item_count": 9, "items": [{"product_title": "P" * 400, "quantity": 9}]})
    assert len(s.note()) <= 500 and s.note().startswith("Real browser")


def test_note_uses_at_most_six_notes():
    s = browser.Session(ran=True, device="phone", notes=[f"step{i}" for i in range(10)])
    assert "step5" in s.note() and "step6" not in s.note()


def test_note_has_no_screenshot_data():
    s = browser.Session(ran=True, device="phone", shot="SECRETSHOTDATA", notes=["opened /"])
    assert "SECRETSHOTDATA" not in s.note()


def test_as_reply_carries_page_and_cart():
    cart = {"item_count": 2, "currency": "EUR", "total_price": 100, "items": [{"product_title": "A", "quantity": 2}]}
    s = browser.Session(device="laptop", status_code=200, url="u", text="T", html="<p>T</p>", cart=cart)
    r = s.as_reply()
    assert (r.device, r.url, r.status_code, r.text, r.html, r.json) == ("laptop", "u", 200, "T", "<p>T</p>", cart)
    assert r.summary.startswith("Cart has 2 items") and r.blocked is False and r.error is None
    assert browser.Session(device="phone").as_reply().summary is None


# ================================================================ clean_steps

def test_empty_means_none():
    for raw in (None, [], ""):
        assert browser.clean_steps(raw) is None


def test_valid_list_round_trips():
    raw = [{"goto": "/products/solaris"}, {"click": "text=Sand"}, {"click": "css=button[name=add]", "optional": True},
           {"wait": 2}, {"scroll": "bottom"}, {"scroll": 300}]
    assert browser.clean_steps(raw) == [
        {"goto": "/products/solaris"}, {"click": "text=Sand"}, {"click": "css=button[name=add]", "optional": True},
        {"wait": 2.0}, {"scroll": "bottom"}, {"scroll": 300}]


def test_click_without_prefix_gets_text_and_is_trimmed():
    assert browser.clean_steps([{"click": "  Add to cart "}]) == [{"click": "text=Add to cart"}]
    assert browser.clean_steps([{"click": "css=.btn"}]) == [{"click": "css=.btn"}]


def test_optional_only_counts_when_true():
    assert browser.clean_steps([{"click": "Sand", "optional": "yes"}]) == [{"click": "text=Sand"}]
    assert browser.clean_steps([{"click": "Sand", "optional": False}]) == [{"click": "text=Sand"}]


def test_input_list_is_not_modified():
    raw = [{"click": "Sand"}]
    browser.clean_steps(raw)
    assert raw == [{"click": "Sand"}]


@pytest.mark.parametrize("bad", ["https://evil.example/x", "//evil.example/x", "products/solaris", "", "http://x",
                                 "\\evil", 5, None, ["/x"], "/" + "a" * 300])
def test_goto_must_be_a_same_site_path(bad):
    with pytest.raises(ValueError, match="must start with /"):
        browser.clean_steps([{"goto": bad}])


def test_goto_of_exactly_300_characters_is_fine():
    path = "/" + "a" * 299
    assert browser.clean_steps([{"goto": path}]) == [{"goto": path}]


def test_up_to_eight_steps_and_no_more():
    ok = [{"goto": "/a"}] * 8
    assert len(browser.clean_steps(ok)) == 8
    with pytest.raises(ValueError, match="at most 8"):
        browser.clean_steps([{"goto": "/a"}] * 9)


@pytest.mark.parametrize("bad", [{"goto": "/a"}, "abc", 5, True])
def test_steps_must_be_a_list(bad):
    with pytest.raises(ValueError):
        browser.clean_steps(bad)


@pytest.mark.parametrize("bad", ["click", 5, None, ["goto"]])
def test_each_step_must_be_an_object(bad):
    with pytest.raises(ValueError, match="one action"):
        browser.clean_steps([bad])


@pytest.mark.parametrize("label", ["Buy it now", "Pay now", "Log in", "Place order", "Sign up", "buy now", "BUY IT NOW",
                                   "Login", "Sign in", "Signup", "Subscribe", "Register", "Create account",
                                   "Complete order", "Confirm order", "Submit order", "Spin", "Pay", "Unlock",
                                   "Yes, please sign up!", "Click here to log in"])
def test_forbidden_clicks_are_rejected_with_a_plain_value_error(label):
    for spec in (label, f"text={label}", f"css={label}"):
        with pytest.raises(ValueError) as e:
            browser.clean_steps([{"click": spec}])
        assert type(e.value) is ValueError
        assert "never click" in str(e.value) and "Traceback" not in str(e.value)


def test_forbidden_message_names_the_button():
    with pytest.raises(ValueError) as e:
        browser.clean_steps([{"click": "Buy it now"}])
    assert str(e.value) == 'We never click "Buy it now": it could pay, order, log in or sign up.'


@pytest.mark.parametrize("label", ["Add to cart", "Sand", "Add to bag", "Checkout", "Check out", "Menu", "Sign out",
                                   "Log out", "Payments info", "Shipping & Payment", "Open menu", "View cart"])
def test_harmless_clicks_are_allowed(label):
    assert browser.clean_steps([{"click": label}]) == [{"click": f"text={label}"}]


@pytest.mark.parametrize("bad", ["", "   ", 5, None, "x" * 121])
def test_click_needs_something_to_click(bad):
    with pytest.raises(ValueError):
        browser.clean_steps([{"click": bad}])


@pytest.mark.parametrize("bad", ["text=", "text=   ", "css=", "css=  "])
def test_click_with_an_empty_target_after_the_prefix_is_rejected(bad):
    with pytest.raises(ValueError):
        browser.clean_steps([{"click": bad}])


@pytest.mark.parametrize("raw,want", [(2, 2.0), (99, 5.0), (-3, 0.0), ("2", 2.0), (0.5, 0.5), (True, 1.0),
                                      ("inf", 5.0), (float("nan"), 0.0)])
def test_wait_is_clamped_between_0_and_5(raw, want):
    assert browser.clean_steps([{"wait": raw}]) == [{"wait": want}]


@pytest.mark.parametrize("bad", ["soon", None, [], {}])
def test_wait_must_be_a_number(bad):
    with pytest.raises(ValueError, match="number of seconds"):
        browser.clean_steps([{"wait": bad}])


@pytest.mark.parametrize("raw,want", [("bottom", "bottom"), (300, 300), ("300", 300), (0, 0), (None, 0), (12.7, 12)])
def test_scroll_values(raw, want):
    assert browser.clean_steps([{"scroll": raw}]) == [{"scroll": want}]


@pytest.mark.parametrize("bad", [{"type": "hover"}, {}, {"hover": "text=Menu"}, {"fill": "x"}, {"type": "x", "value": "y"}])
def test_unknown_action_is_rejected(bad):
    with pytest.raises(ValueError, match="open a page, click, wait or scroll"):
        browser.clean_steps([bad])


@pytest.mark.parametrize("bad", [[1], {"y": 1}])
def test_scroll_with_a_list_or_object_is_a_value_error(bad):
    with pytest.raises(ValueError):
        browser.clean_steps([{"scroll": bad}])


def test_scroll_text_error_is_in_plain_words():
    with pytest.raises(ValueError) as e:
        browser.clean_steps([{"scroll": "abc"}])
    assert "invalid literal" not in str(e.value)


@pytest.mark.parametrize("label", ["Log-in", "Sign-in", "Sign-up"])
def test_hyphenated_login_and_signup_clicks_are_forbidden(label):
    with pytest.raises(ValueError):
        browser.clean_steps([{"click": label}])


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_forbidden_pattern_is_the_same_in_javascript():
    """browser_fn.mjs does `new RegExp(context.forbidden, "i")`: the Python pattern must mean the same there."""
    labels = ["Buy it now", "Pay now", "Log in", "Place order", "Sign up", "Add to cart", "Sand", "Payments info"]
    script = ("const re = new RegExp(process.argv[1], 'i');"
              "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(s => re.test(s))));")
    out = subprocess.run(["node", "-e", script, browser.FORBIDDEN, json.dumps(labels)],
                         capture_output=True, text=True, timeout=30, check=True).stdout
    assert json.loads(out) == [True, True, True, True, True, False, False, False]
