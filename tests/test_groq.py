"""Tests for api/_lib/groq.py. No network: requests.post is mocked."""
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from api._lib import groq
from api._lib.groq import GroqError

SITE = "https://shop.example.com"


def reply(obj, status=200, raw=None):
    """A fake requests response whose message content is JSON (or raw text)."""
    r = MagicMock()
    r.status_code = status
    content = raw if raw is not None else json.dumps(obj)
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    return r


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")


def post(*responses):
    return patch("api._lib.groq.requests.post", side_effect=list(responses))


# ---- chat_json

def test_chat_json_parses_and_sends_expected_request():
    with post(reply({"a": 1})) as p:
        assert groq.chat_json("sys", "usr") == {"a": 1}
    kwargs = p.call_args.kwargs
    assert p.call_args.args[0] == "https://api.groq.com/openai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert 24 < kwargs["timeout"] <= 25
    body = kwargs["json"]
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0.2
    assert body["reasoning_effort"] == "low"


def test_chat_json_strips_fences():
    with post(reply(None, raw='```json\n{"a": 2}\n```')):
        assert groq.chat_json("s", "u") == {"a": 2}


def test_chat_json_retries_once_then_succeeds():
    with post(requests.Timeout(), reply({"ok": True})) as p:
        assert groq.chat_json("s", "u") == {"ok": True}
    assert p.call_count == 2


def test_chat_json_waits_when_rate_limited_then_retries():
    limited = reply(None, status=429)
    limited.headers = {"retry-after": "1.5"}
    with post(limited, reply({"ok": True})) as p, patch("api._lib.groq.time.sleep") as sleep:
        assert groq.chat_json("s", "u") == {"ok": True}
    assert p.call_count == 2
    assert sleep.call_args.args[0] == pytest.approx(1.5, abs=0.1)


def test_chat_json_rate_limit_wait_stays_inside_budget():
    limited = reply(None, status=429)
    limited.headers = {"retry-after": "20"}
    with post(limited, reply({"ok": True})), patch("api._lib.groq.time.sleep") as sleep:
        groq.chat_json("s", "u", timeout=10)
    assert sleep.call_args.args[0] <= 7


def test_chat_json_retries_once_then_raises():
    with post(reply(None, status=500), reply(None, raw="not json")) as p:
        with pytest.raises(GroqError, match="didn't answer"):
            groq.chat_json("s", "u")
    assert p.call_count == 2


def test_chat_json_missing_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    with post() as p:
        with pytest.raises(GroqError, match="key is not set up"):
            groq.chat_json("s", "u")
    assert p.call_count == 0


def test_strip_text():
    assert groq.strip_text("a \n\t b   c") == "a b c"
    assert len(groq.strip_text("x" * 9000)) == 6000
    assert groq.strip_text("abcdef", 3) == "abc"


# ---- normalize_draft

def test_full_same_site_url_is_stripped():
    d = groq.normalize_draft({"user_does": "a", "good_result": "b",
                              "request_url": "https://shop.example.com/search?q=sun+glasses"}, SITE)
    assert d["request_url"] == "/search?q=sun+glasses"


def test_other_host_rejected():
    for url in ("https://evil.com/x", "//evil.com/x", "javascript:alert(1)", "", None):
        d = groq.normalize_draft({"user_does": "a", "good_result": "b", "request_url": url}, SITE)
        assert d["request_url"] == "/"


def test_relative_path_gets_slash():
    d = groq.normalize_draft({"request_url": "products/solaris"}, SITE)
    assert d["request_url"] == "/products/solaris"


def test_bad_rule_dropped_and_decided_by_forced():
    d = groq.normalize_draft({"checks": [
        {"decided_by": "ai", "rule": "text_has", "expected": "Solaris"},
        {"decided_by": "code", "rule": "nonsense", "expected": "x"},
        {"decided_by": "code", "rule": "ai_judge", "expected": "Is it there?"},
        {"decided_by": "code", "rule": "manual", "expected": "Look at the photo"},
        {"decided_by": "human", "rule": "min_results", "expected": 3},
    ]}, SITE)
    rules = [(c["rule"], c["decided_by"], c["expected"]) for c in d["checks"]]
    assert rules == [
        ("status_ok", "code", None),
        ("text_has", "code", "Solaris"),
        ("ai_judge", "ai", "Is it there?"),
        ("manual", "human", "Look at the photo"),
        ("min_results", "code", "3"),
    ]


def test_empty_expected_dropped():
    d = groq.normalize_draft({"checks": [
        {"rule": "text_has", "expected": "  "}, {"rule": "text_absent", "expected": None},
        {"rule": "ai_judge", "expected": ""}, {"rule": "manual"},
        {"rule": "status_ok", "expected": "junk"},
    ]}, SITE)
    assert d["checks"] == [{"decided_by": "code", "rule": "status_ok", "expected": None}]


def test_get_body_none_and_post_string_body_parsed():
    get = groq.normalize_draft({"method": "get", "request_body": {"a": 1}}, SITE)
    assert get["method"] == "GET" and get["request_body"] is None
    post_d = groq.normalize_draft({"method": "post", "request_url": "/cart/add.js",
                                   "request_body": '{"items": []}'}, SITE)
    assert post_d["method"] == "POST" and post_d["request_body"] == {"items": []}
    bad = groq.normalize_draft({"method": "DELETE", "request_body": "oops"}, SITE)
    assert bad["method"] == "GET" and bad["request_body"] is None


def test_checks_capped_at_six_with_status_ok_first():
    many = [{"rule": "text_has", "expected": f"w{i}"} for i in range(10)]
    d = groq.normalize_draft({"checks": many}, SITE)
    assert len(d["checks"]) == 6
    assert d["checks"][0]["rule"] == "status_ok"


def test_text_capped_and_nonempty():
    d = groq.normalize_draft({"user_does": "x" * 900, "good_result": ""}, SITE)
    assert len(d["user_does"]) == 500
    assert d["good_result"]


# ---- jobs

def test_tidy_pair():
    ai = {"user_does": "Searches for Solaris", "good_result": "Solaris shows up",
          "request_url": "/search?q=Solaris", "method": "GET", "request_body": None,
          "checks": [{"decided_by": "code", "rule": "text_has", "expected": "Solaris"}]}
    with post(reply(ai)):
        d = groq.tidy_pair("i search solaris", SITE)
    assert d["request_url"] == "/search?q=Solaris"
    assert [c["rule"] for c in d["checks"]] == ["status_ok", "text_has"]


def test_tidy_pair_unusable_answer_raises():
    with post(reply({"user_does": ""})):
        with pytest.raises(GroqError):
            groq.tidy_pair("x", SITE)


def test_change_to_pair():
    ai = {"pair": {"user_does": "Opens the shipping page", "good_result": "It lists delivery times",
                   "request_url": "/pages/shipping", "checks": []}}
    with post(reply(ai)):
        d = groq.change_to_pair("added a shipping page", SITE)
    assert d["request_url"] == "/pages/shipping"


def test_suggest_pairs_capped_at_five():
    pairs = [{"user_does": f"does {i}", "good_result": f"gets {i}", "request_url": "/"} for i in range(8)]
    with post(reply({"pairs": pairs})):
        out = groq.suggest_pairs("home text", SITE)
    assert len(out) == 5
    assert all(p["checks"][0]["rule"] == "status_ok" for p in out)


def test_suggest_pairs_sends_stripped_text():
    with post(reply({"pairs": []})) as p:
        groq.suggest_pairs("word " * 5000, SITE)
    user = p.call_args.kwargs["json"]["messages"][1]["content"]
    assert len(json.loads(user)["home_page_text"]) <= 6000


PAIR = {"user_does": "Searches Solaris", "good_result": "Solaris is listed"}
AI = [{"id": "a1", "expected": "Does the page show battery runtime?"}]
CODE = [{"id": "c1", "rule": "text_has", "expected": "Solaris",
         "detail": "'Solaris' was not found on the page."}]


def test_judge_empty_lists_no_call():
    with post() as p:
        assert groq.judge("page", PAIR, [], []) == {}
    assert p.call_count == 0


def test_judge_happy_path():
    ai = {"results": [
        {"id": "a1", "passed": True, "why": "The page says 12 hours of battery."},
        {"id": "c1", "passed": True, "why": "No product called Solaris is listed."},
    ]}
    with post(reply(ai)) as p:
        out = groq.judge("page", PAIR, AI, CODE)
    assert p.call_count == 1
    assert out["a1"] == {"passed": True, "why": "The page says 12 hours of battery."}
    assert out["c1"] == {"passed": False, "why": "No product called Solaris is listed."}


def test_judge_validates_output():
    ai = {"results": [{"id": "a1", "passed": "yes", "why": "x"},
                      {"id": "c1", "why": "line one\nline two " + "z" * 400}]}
    with post(reply(ai)):
        out = groq.judge("page", PAIR, AI, CODE)
    assert out["a1"] == {"passed": None, "why": "AI could not judge, please look"}
    assert out["c1"]["passed"] is False
    assert "\n" not in out["c1"]["why"] and len(out["c1"]["why"]) <= 200


def test_judge_falls_back_on_error():
    with post(requests.Timeout(), requests.Timeout()):
        out = groq.judge("page", PAIR, AI, CODE)
    assert out["a1"] == {"passed": None, "why": "AI could not judge, please look"}
    assert out["c1"] == {"passed": False, "why": "'Solaris' was not found on the page."}


ITEMS = [{"result_id": "r1", "user_does": "Searches Solaris", "good_result": "Solaris is listed",
          "device": "phone", "status_code": 200,
          "failed_checks": [{"rule": "text_has", "expected": "Solaris",
                             "why": "'Solaris' was not found on the page."}],
          "what_site_said": "No results found"}]


def test_diagnose_happy_path_and_limit():
    items = [{**ITEMS[0], "result_id": f"r{i}"} for i in range(5)]
    ai = {"points": [{"result_id": "r0", "explanation": "Search shows no results. Add the product."}]}
    with post(reply(ai)) as p:
        out = groq.diagnose(items)
    sent = json.loads(p.call_args.kwargs["json"]["messages"][1]["content"])["failed_tests"]
    assert len(sent) == 3
    assert out["r0"] == "Search shows no results. Add the product."
    assert out["r1"] and out["r2"] and "r3" not in out


def test_diagnose_fallback_on_error():
    with post(requests.Timeout(), requests.Timeout()):
        out = groq.diagnose(ITEMS)
    assert "'Solaris' was not found on the page." in out["r1"]


def test_diagnose_fallback_never_empty():
    bare = [{"result_id": "r9", "good_result": "Cart has 1 item", "failed_checks": []}]
    with post(requests.Timeout(), requests.Timeout()):
        assert groq.diagnose(bare)["r9"]
