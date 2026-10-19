"""Tests for groq.judge_screenshot (the vision judge) in api/_lib/groq.py. No network: requests.post is mocked."""
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from api._lib import groq

PAIR = {"user_does": "Opens the menu on a phone", "good_result": "The menu is open and readable"}
SHOT = "QUJDREVG"  # any base64 text
URL = "https://api.groq.com/openai/v1/chat/completions"


def reply(results=None, status=200, headers=None, raw=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    content = raw if raw is not None else json.dumps({"results": results or []})
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    return r


def answer(cid, passed=True, why="I can see it", confident=True, **extra):
    d = {"id": str(cid), "passed": passed, "why": why}
    if confident is not None:
        d["confident"] = confident
    d.update(extra)
    return d


def checks(*ids):
    return [{"id": i, "expected": f"Question {i}?"} for i in ids]


def post(*responses):
    return patch("api._lib.groq.requests.post", side_effect=list(responses))


def asked_ids(call) -> list[str]:
    """The check ids that one request asked about (from the text part of the user message)."""
    text = call.kwargs["json"]["messages"][1]["content"][0]["text"]
    return [c["id"] for c in json.loads(text)["checks"]]


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")


def unsure(c):
    return {"passed": None, "why": "The AI couldn't tell from the screenshot", "confident": False}


# ---------------------------------------------------------------- nothing to ask

def test_no_key_gives_unsure_for_every_check_and_no_call(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    with post() as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a", "b"), "phone")
    assert out == {"a": unsure("a"), "b": unsure("b")}
    assert p.call_count == 0


def test_blank_key_counts_as_no_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "   ")
    with post() as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert out == {"a": unsure("a")} and p.call_count == 0


@pytest.mark.parametrize("shot", ["", None])
def test_no_screenshot_gives_unsure_and_no_call(shot):
    with post() as p:
        out = groq.judge_screenshot(shot, PAIR, checks("a", "b"), "laptop")
    assert out == {"a": unsure("a"), "b": unsure("b")} and p.call_count == 0


def test_no_checks_gives_nothing_and_no_call():
    with post() as p:
        assert groq.judge_screenshot(SHOT, PAIR, [], "phone") == {}
    assert p.call_count == 0


def test_oversize_screenshot_is_not_sent():
    big = "A" * (groq.VISION_MAX_B64 + 1)
    with post() as p:
        out = groq.judge_screenshot(big, PAIR, checks("a"), "phone")
    assert out == {"a": unsure("a")} and p.call_count == 0


def test_screenshot_at_exactly_the_limit_is_sent():
    edge = "A" * groq.VISION_MAX_B64
    with post(reply([answer("a")])) as p:
        out = groq.judge_screenshot(edge, PAIR, checks("a"), "phone")
    assert p.call_count == 1 and out["a"]["confident"] is True


def test_too_little_time_left_makes_no_call():
    with post() as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone", timeout=3)
    assert out == {"a": unsure("a")} and p.call_count == 0


# ---------------------------------------------------------------- confident answers

def test_confident_answers_map_by_id():
    ans = [answer("a", True, "Menu is open"), answer("b", False, "The text is cut off")]
    with post(reply(ans)) as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a", "b"), "phone")
    assert p.call_count == 1
    assert out == {"a": {"passed": True, "why": "Menu is open", "confident": True},
                   "b": {"passed": False, "why": "The text is cut off", "confident": True}}


def test_answers_in_a_different_order_still_map_by_id():
    with post(reply([answer("b", False, "no"), answer("a", True, "yes")])) as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a", "b"), "phone")
    assert out["a"]["passed"] is True and out["b"]["passed"] is False and p.call_count == 1


def test_ids_may_be_non_strings_and_keep_their_own_type():
    with post(reply([answer(7, True, "ok")])):
        out = groq.judge_screenshot(SHOT, PAIR, checks(7), "phone")
    assert out[7]["passed"] is True


def test_missing_confident_field_is_not_trusted():
    # Only an explicit confident: true counts; anything else is asked again, then handed to a person.
    with post(reply([answer("a", True, "ok", confident=None)])):
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")["a"]
    assert out["confident"] is False and out["passed"] is None


def test_missing_why_gets_a_default_and_long_why_is_cut():
    with post(reply([answer("a", True, ""), answer("b", False, "w" * 900)])):
        out = groq.judge_screenshot(SHOT, PAIR, checks("a", "b"), "phone")
    assert out["a"]["why"] == "Judged from the screenshot."
    assert len(out["b"]["why"]) <= groq.MAX_WHY


def test_unknown_ids_and_junk_rows_are_ignored():
    with post(reply([answer("zzz"), "junk", 5, answer("a")])):
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert list(out) == ["a"] and out["a"]["confident"] is True


def test_non_boolean_passed_is_unsure():
    with post(reply([answer("a", "true")]), reply([answer("a", None)])) as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert out["a"] == unsure("a") and p.call_count == 2


# ---------------------------------------------------------------- the second try

def test_unsure_then_sure_asks_only_about_the_unsure_check_the_second_time():
    first = reply([answer("a", True, "ok"), answer("b", True, "can't see", confident=False)])
    second = reply([answer("b", False, "Now I can see it: overlap")])
    with post(first, second) as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a", "b"), "phone")
    assert p.call_count == 2
    assert asked_ids(p.call_args_list[0]) == ["a", "b"]
    assert asked_ids(p.call_args_list[1]) == ["b"]
    assert out["a"] == {"passed": True, "why": "ok", "confident": True}
    assert out["b"] == {"passed": False, "why": "Now I can see it: overlap", "confident": True}


def test_a_check_missing_from_the_first_answer_is_asked_again():
    with post(reply([answer("a")]), reply([answer("b", True, "ok")])) as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a", "b"), "phone")
    assert asked_ids(p.call_args_list[1]) == ["b"]
    assert out["b"]["confident"] is True


def test_unsure_twice_is_passed_none_and_not_confident():
    bad = lambda: reply([answer("a", True, "maybe", confident=False)])  # noqa: E731
    with post(bad(), bad()) as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert p.call_count == 2
    assert out["a"] == {"passed": None, "why": "The AI couldn't tell from the screenshot", "confident": False}


def test_never_asks_a_third_time():
    with post(reply([]), reply([]), reply([answer("a")])) as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert p.call_count == 2 and out["a"]["confident"] is False


def test_sure_on_the_first_try_means_one_call_only():
    with post(reply([answer("a")])) as p:
        groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert p.call_count == 1


def test_a_timeout_or_error_burns_one_try_then_the_second_can_succeed():
    with post(requests.Timeout(), reply([answer("a", True, "ok")])) as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert p.call_count == 2 and out["a"]["passed"] is True


def test_http_error_and_junk_json_end_unsure_without_raising():
    with post(reply(status=500), reply(None, raw="not json at all")) as p:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert p.call_count == 2 and out["a"] == unsure("a")


# ---------------------------------------------------------------- the request

def test_request_uses_the_vision_model_json_mode_and_an_image_data_url():
    with post(reply([answer("a")])) as p:
        groq.judge_screenshot(SHOT, PAIR, checks("a"), "laptop")
    assert p.call_args.args[0] == URL
    assert p.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"
    body = p.call_args.kwargs["json"]
    assert body["model"] == "qwen/qwen3.8-27b" == groq.VISION_MODEL
    assert body["response_format"] == {"type": "json_object"}
    system, user = body["messages"]
    assert system["role"] == "system" and system["content"] == groq.VISION_SYSTEM
    parts = user["content"]
    assert [x["type"] for x in parts] == ["text", "image_url"]
    url = parts[1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,") and url == f"data:image/jpeg;base64,{SHOT}"
    info = json.loads(parts[0]["text"])
    assert info["device"] == "laptop"
    assert info["golden_pair"] == PAIR
    assert info["checks"] == [{"id": "a", "question": "Question a?"}]
    assert 0 < p.call_args.kwargs["timeout"] <= groq.TIMEOUT_SECONDS


def test_all_checks_travel_in_one_request_with_one_image():
    with post(reply([answer("a"), answer("b"), answer("c")])) as p:
        groq.judge_screenshot(SHOT, PAIR, checks("a", "b", "c"), "phone")
    assert p.call_count == 1 and asked_ids(p.call_args) == ["a", "b", "c"]
    images = [x for x in p.call_args.kwargs["json"]["messages"][1]["content"] if x["type"] == "image_url"]
    assert len(images) == 1


def test_screenshot_is_not_part_of_the_text_prompt_or_system_prompt():
    with post(reply([answer("a")])) as p:
        groq.judge_screenshot("UNIQUESHOTDATA", PAIR, checks("a"), "phone")
    body = p.call_args.kwargs["json"]
    assert "UNIQUESHOTDATA" not in body["messages"][0]["content"]
    assert "UNIQUESHOTDATA" not in body["messages"][1]["content"][0]["text"]


# ---------------------------------------------------------------- rate limit

def test_429_with_retry_after_waits_then_retries():
    limited = reply(status=429, headers={"retry-after": "1.5"})
    with post(limited, reply([answer("a", True, "ok")])) as p, patch("api._lib.groq.time.sleep") as sleep:
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert p.call_count == 2
    assert sleep.call_args.args[0] == pytest.approx(1.5, abs=0.1)
    assert out["a"] == {"passed": True, "why": "ok", "confident": True}


def test_429_without_retry_after_waits_a_short_default():
    with post(reply(status=429, headers={}), reply([answer("a")])), patch("api._lib.groq.time.sleep") as sleep:
        groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert 0 < sleep.call_args.args[0] <= 20


def test_429_wait_never_runs_past_the_time_budget():
    limited = reply(status=429, headers={"retry-after": "20"})
    with post(limited, reply([answer("a")])), patch("api._lib.groq.time.sleep") as sleep:
        groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone", timeout=6)
    assert sleep.call_args.args[0] <= 2.5


def test_429_twice_ends_unsure_without_raising():
    limited = lambda: reply(status=429, headers={"retry-after": "1"})  # noqa: E731
    with post(limited(), limited()) as p, patch("api._lib.groq.time.sleep"):
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert p.call_count == 2 and out["a"] == unsure("a")


# ---------------------------------------------------------------- odd model output

@pytest.mark.parametrize("value", ["false", "False", 0])
def test_confident_given_as_text_or_zero_is_not_trusted(value):
    one = lambda: reply([answer("a", True, "guess", confident=value)])  # noqa: E731
    with post(one(), one()):
        out = groq.judge_screenshot(SHOT, PAIR, checks("a"), "phone")
    assert out["a"]["passed"] is None and out["a"]["confident"] is False
