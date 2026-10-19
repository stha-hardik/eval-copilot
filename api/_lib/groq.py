"""Groq helper: the five AI jobs of Eval Co-pilot, plus the code that keeps AI output safe."""
import json
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
TIMEOUT_SECONDS = 25
REASONING_HEADROOM = 800  # gpt-oss "thinks" inside the token budget; leave room for the answer
MAX_CHECKS = 6
MAX_TEXT = 500
MAX_EXPECTED = 300
MAX_WHY = 200
MAX_EXPLANATION = 600
AI_UNSURE = "AI could not judge, please look"

CODE_RULES = {"status_ok", "text_has", "text_absent", "count_equals", "min_results"}
RULE_DECIDER = {**{r: "code" for r in CODE_RULES}, "ai_judge": "ai", "manual": "human"}
NEEDS_EXPECTED = {"text_has", "text_absent", "ai_judge", "manual"}


class GroqError(Exception):
    """The AI step failed. The message is plain words that can be shown to the builder."""


# ---------------------------------------------------------------- prompts

SHOP_RULES = """\
About the site: it is usually a Shopify store. Request paths:
- search: /search?q=<words> (URL-encode, use + for spaces)
- collection: /collections/<handle>
- product: /products/<handle>; product data: /products/<handle>.json
- cart contents: /cart.js
- add to cart: POST /cart/add.js with body {"items":[{"handle":"<product-handle>","option":"<colour or variant name or null>","quantity":1}]} (the server finds the variant id).
Handles are lowercase-hyphenated product names. They are a best guess; the builder will check them.

Our tester reads pages with plain HTTP: no browser, no JavaScript, no clicks, no screenshots. So:
- Layout, overlap, colours or images matching, pop-ups, "easy to find", checkout or payment pages -> a "manual" check (a human looks). expected = what the human should look at.
- A fact in the page text (for example "mentions battery runtime") -> an "ai_judge" check whose expected is a yes/no question, or a "text_has" check for one exact word or phrase.
- Page should load -> "status_ok" (expected null).
- Items in a cart -> "count_equals" with expected like "item_count=1".
- A search that returns products -> "min_results" with expected like "1".
- "text_absent" when a word must NOT appear.
Give 2 to 5 checks per pair, each small and testable, in plain words. The golden pair is the standard.
Never invent numbers, prices, status codes or counts.
"""

DRAFT_SHAPE = """\
{"user_does": "what a shopper does, one plain sentence",
 "good_result": "what a good result has, one plain sentence",
 "request_url": "/path?query",
 "method": "GET" or "POST",
 "request_body": null or an object (POST only),
 "checks": [{"decided_by": "code"|"ai"|"human",
             "rule": "status_ok"|"text_has"|"text_absent"|"count_equals"|"min_results"|"ai_judge"|"manual",
             "expected": string or null}]}
decided_by is "code" for status_ok/text_has/text_absent/count_equals/min_results, "ai" for ai_judge, "human" for manual."""

JSON_ONLY = "Answer with JSON only, in exactly the given shape. No other text."

TIDY_SYSTEM = f"""You help a website builder write a "golden pair": what a user does + what a good result has.
The builder typed or spoke a rough note. Turn it into one clean golden pair that our tester can run.
Keep the builder's meaning; do not add new goals.

{SHOP_RULES}
{JSON_ONLY}
Shape:
{DRAFT_SHAPE}"""

SUGGEST_SYSTEM = f"""You are a conversion-rate (CRO) expert reviewing the text of a shop's home page.
Propose up to 5 golden pairs a real shopper would try that matter for sales: search, a category,
product page facts, add to cart, shipping or returns info, and similar. Use product names and links
you can see in the page text; if you must guess a handle, keep it lowercase-hyphenated.
Each pair is: what a user does + what a good result has.

{SHOP_RULES}
{JSON_ONLY}
Shape:
{{"pairs": [ {DRAFT_SHAPE} ]}}"""

JUDGE_SYSTEM = f"""You are a careful checker for a website tester. You get the text of one page, the golden pair
(what the shopper does and what a good result has), and two lists.
1. "ai_checks": each has an id and a yes/no question. Decide from the page text only. passed is true or false.
   "why" is one short line that cites what the page shows (or does not show).
2. "failed_code_checks": checks the code already found failing. Each has an id, rule, expected and detail
   (what the code found). Do NOT change the result. Write one short plain-words line in "why":
   what is wrong for the shopper, grounded in the detail.
Never invent numbers, status codes or counts; use only what is in the input. Plain words, one line each, under 180 characters.
{JSON_ONLY}
Shape:
{{"results": [{{"id": "<id from the input>", "passed": true or false, "why": "one line"}}]}}
Include every id from both lists. For failed_code_checks set passed to false."""

DIAGNOSE_SYSTEM = f"""You explain to a website builder why shoppers are stuck. You get up to 3 failed tests.
Each has: result_id, user_does, good_result, device, status_code, failed_checks (rule, expected, why) and
what_site_said (what the site actually returned).
For each, write 1 to 3 plain-word sentences: what is broken for the shopper, backed by what the site showed,
and what to change. Never invent numbers, status codes or counts; use only what is in the input.
Do not use code jargon.
{JSON_ONLY}
Shape:
{{"points": [{{"result_id": "<result_id from the input>", "explanation": "1 to 3 sentences"}}]}}"""

CHANGE_SYSTEM = f"""A website builder wrote what else they changed on their site. Turn it into ONE new golden pair
(what a user does + what a good result has) with checks that would prove the change worked.
Pick the single most important change if there are several.

{SHOP_RULES}
{JSON_ONLY}
Shape:
{DRAFT_SHAPE}"""


# ---------------------------------------------------------------- Groq call

def _parse_json(content: str) -> dict:
    """Parse model text as a JSON object; tolerate ``` fences and chatter around it."""
    text = (content or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON root is not an object")
    return data


def _call_once(headers: dict, payload: dict, timeout: float) -> dict:
    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Groq answered {resp.status_code}")
    return _parse_json(resp.json()["choices"][0]["message"]["content"])


def chat_json(system: str, user: str, max_tokens: int = 1500, timeout: float = TIMEOUT_SECONDS) -> dict:
    """Ask Groq for a JSON object. Retries once (if time allows); raises GroqError if it still fails.

    `timeout` is the total time budget in seconds for both attempts.
    """
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise GroqError("The AI key is not set up on the server.")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "reasoning_effort": "low",
        "max_completion_tokens": max_tokens + REASONING_HEADROOM,
    }
    deadline = time.monotonic() + timeout
    for _ in range(2):
        left = deadline - time.monotonic()
        if left < 3:
            break
        try:
            return _call_once(headers, payload, min(left, TIMEOUT_SECONDS))
        except Exception:  # timeout, HTTP error, bad JSON: all get one retry
            continue
    raise GroqError("The AI didn't answer. Please try again.")


# ---------------------------------------------------------------- cleaning

def strip_text(text: Any, limit: int = 6000) -> str:
    """Collapse whitespace and cut to `limit` characters."""
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _clean_str(value: Any, cap: int) -> str:
    return strip_text(value, cap) if isinstance(value, (str, int, float)) else ""


def _clean_path(value: Any, site_url: str) -> str:
    """Return a same-site path starting with "/", or "/" when unsafe or empty."""
    raw = re.sub(r"\s+", "", str(value or "")).replace("\\", "/")
    if not raw:
        return "/"
    parts = urlparse(raw)
    if parts.netloc:
        host = lambda h: h.lower().removeprefix("www.")
        if host(parts.netloc) != host(urlparse(site_url).netloc):
            return "/"
        raw = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    elif parts.scheme:
        return "/"
    if not raw.startswith("/"):
        raw = "/" + raw
    return "/" + raw.lstrip("/")


def _clean_body(value: Any) -> dict | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) and value else None


def _clean_checks(checks: Any) -> list[dict]:
    out: list[dict] = []
    for c in checks if isinstance(checks, list) else []:
        if not isinstance(c, dict):
            continue
        rule = str(c.get("rule") or "").strip().lower()
        if rule not in RULE_DECIDER:
            continue
        expected = _clean_str(c.get("expected"), MAX_EXPECTED) or None
        if rule == "status_ok":
            expected = None
        if rule in NEEDS_EXPECTED and not expected:
            continue
        out.append({"decided_by": RULE_DECIDER[rule], "rule": rule, "expected": expected})
    if not any(c["rule"] == "status_ok" for c in out):
        out.insert(0, {"decided_by": "code", "rule": "status_ok", "expected": None})
    return out[:MAX_CHECKS]


def normalize_draft(d: dict, site_url: str) -> dict:
    """Turn any AI output into a safe, valid Draft."""
    d = d if isinstance(d, dict) else {}
    method = str(d.get("method") or "GET").strip().upper()
    method = method if method in ("GET", "POST") else "GET"
    return {
        "user_does": _clean_str(d.get("user_does"), MAX_TEXT) or "A shopper uses the site",
        "good_result": _clean_str(d.get("good_result"), MAX_TEXT) or "The site works as the shopper expects",
        "request_url": _clean_path(d.get("request_url"), site_url),
        "method": method,
        "request_body": _clean_body(d.get("request_body")) if method == "POST" else None,
        "checks": _clean_checks(d.get("checks")),
    }


def _has_pair_text(d: Any) -> bool:
    return isinstance(d, dict) and bool(_clean_str(d.get("user_does"), 1)) and bool(_clean_str(d.get("good_result"), 1))


def _one_line(value: Any, cap: int = MAX_WHY) -> str:
    return strip_text(value, cap) if isinstance(value, str) else ""


def _user_json(**parts: Any) -> str:
    return json.dumps(parts, ensure_ascii=False)


# ---------------------------------------------------------------- the five jobs

def _single_draft(system: str, user: str, site_url: str) -> dict:
    data = chat_json(system, user, max_tokens=1200)
    if isinstance(data.get("pair"), dict):
        data = data["pair"]
    if not _has_pair_text(data):
        raise GroqError("The AI didn't give a usable answer. Please try again.")
    return normalize_draft(data, site_url)


def tidy_pair(rough_text: str, site_url: str) -> dict:
    """Job 1: a rough note becomes one clean golden pair Draft."""
    user = _user_json(site_url=site_url, builder_note=strip_text(rough_text, 2000))
    return _single_draft(TIDY_SYSTEM, user, site_url)


def suggest_pairs(home_text: str, site_url: str) -> list[dict]:
    """Job 2: up to 5 CRO-minded pair Drafts from the home page text."""
    user = _user_json(site_url=site_url, home_page_text=strip_text(home_text))
    data = chat_json(SUGGEST_SYSTEM, user, max_tokens=2500)
    pairs = data.get("pairs")
    pairs = pairs if isinstance(pairs, list) else []
    return [normalize_draft(p, site_url) for p in pairs if _has_pair_text(p)][:5]


def judge(page_text: str, pair: dict, ai_checks: list[dict], failed_code_checks: list[dict],
          timeout: float = TIMEOUT_SECONDS) -> dict:
    """Job 3: one Groq call that answers the AI checks and explains the failed code checks."""
    if not ai_checks and not failed_code_checks:
        return {}
    user = _user_json(
        page_text=strip_text(page_text),
        golden_pair={"user_does": pair.get("user_does", ""), "good_result": pair.get("good_result", "")},
        ai_checks=[{"id": str(c["id"]), "question": c.get("expected")} for c in ai_checks],
        failed_code_checks=[
            {"id": str(c["id"]), "rule": c.get("rule"), "expected": c.get("expected"), "detail": c.get("detail")}
            for c in failed_code_checks
        ],
    )
    try:
        data = chat_json(JUDGE_SYSTEM, user, max_tokens=1200, timeout=timeout)
    except GroqError:
        data = {}
    answers = {
        str(r.get("id")): r
        for r in (data.get("results") if isinstance(data.get("results"), list) else [])
        if isinstance(r, dict)
    }
    out: dict = {}
    for c in ai_checks:
        a = answers.get(str(c["id"]), {})
        passed = a.get("passed") if isinstance(a.get("passed"), bool) else None
        why = _one_line(a.get("why"))
        if passed is None:
            out[c["id"]] = {"passed": None, "why": AI_UNSURE}
        else:
            out[c["id"]] = {"passed": passed, "why": why or "The AI gave no reason."}
    for c in failed_code_checks:
        why = _one_line(answers.get(str(c["id"]), {}).get("why")) or _one_line(c.get("detail"))
        out[c["id"]] = {"passed": False, "why": why}
    return out


def _fallback_explanation(item: dict) -> str:
    whys = [_one_line(f.get("why"), 150) for f in item.get("failed_checks") or [] if isinstance(f, dict)]
    whys = [w for w in whys if w]
    if whys:
        return strip_text("A shopper would get stuck here. " + " ".join(whys), MAX_EXPLANATION)
    return strip_text(f"The site did not give the shopper what was expected: {item.get('good_result') or 'a good result'}", MAX_EXPLANATION)


def diagnose(items: list[dict], timeout: float = TIMEOUT_SECONDS) -> dict:
    """Job 4: plain-word explanation per failed test, `{result_id: explanation}`."""
    items = [i for i in items if isinstance(i, dict)][:3]
    if not items:
        return {}
    slim = [
        {
            "result_id": str(i.get("result_id")),
            "user_does": i.get("user_does"),
            "good_result": i.get("good_result"),
            "device": i.get("device"),
            "status_code": i.get("status_code"),
            "failed_checks": i.get("failed_checks") or [],
            "what_site_said": strip_text(i.get("what_site_said"), 1500),
        }
        for i in items
    ]
    try:
        data = chat_json(DIAGNOSE_SYSTEM, _user_json(failed_tests=slim), max_tokens=1500, timeout=timeout)
    except GroqError:
        data = {}
    points = data.get("points") if isinstance(data.get("points"), list) else []
    said = {str(p.get("result_id")): p.get("explanation") for p in points if isinstance(p, dict)}
    out: dict = {}
    for i in items:
        text = strip_text(said.get(str(i.get("result_id"))), MAX_EXPLANATION) if isinstance(said.get(str(i.get("result_id"))), str) else ""
        out[i.get("result_id")] = text or _fallback_explanation(i)
    return out


def change_to_pair(note: str, site_url: str) -> dict:
    """Job 5: "other things I changed" becomes ONE new golden pair Draft."""
    user = _user_json(site_url=site_url, what_the_builder_changed=strip_text(note, 2000))
    return _single_draft(CHANGE_SYSTEM, user, site_url)
