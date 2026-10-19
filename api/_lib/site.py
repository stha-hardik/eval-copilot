"""Fetch the builder's live site like a phone or a laptop, and decide the simple code checks."""

from __future__ import annotations

import html as _html
import json as _json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from http import HTTPStatus
from typing import Any
from urllib.parse import urlsplit

import requests

UA = {
    "phone": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "laptop": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
TIMEOUT = 15

TEXT_CAP = 200_000
HTML_CAP = 500_000
HOME_TEXT_CAP = 6000
EXCERPT_CAP = 500

TIMEOUT_MESSAGE = "The site took too long to answer (over 15 seconds)."
UNREACHABLE_MESSAGE = "We couldn't reach the site."
CHALLENGE_MARKERS = ("cf-chl", "just a moment...", "captcha", "access denied")
STRONG_CHALLENGE_MARKERS = ("cf-chl", "challenge-platform", "<title>just a moment", "<title>access denied")
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "INR": "₹"}


@dataclass
class SiteReply:
    """What the site answered for one device."""

    device: str
    url: str
    status_code: int | None = None
    blocked: bool = False
    error: str | None = None
    text: str = ""
    json: Any | None = None
    html: str = ""
    summary: str | None = None


# ---------------------------------------------------------------- HTML -> text

_SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
_INLINE_TAGS = {"a", "b", "i", "u", "em", "strong", "span", "small", "sup", "sub", "abbr", "mark", "font"}


class _TextParser(HTMLParser):
    """Collects the title and the visible text of a page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_title = False
        self.title_done = False
        self.title_parts: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self.skip += 1
        elif tag == "title" and not self.skip and not self.title_done:
            self.in_title = True
        if tag not in _INLINE_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
        elif tag == "title" and self.in_title:
            self.in_title = False
            self.title_done = True
        if tag not in _INLINE_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self.in_title:
            self.title_parts.append(data)
        else:
            self.parts.append(data)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_html(html: str) -> str:
    """Turn HTML into readable text: title first, no scripts/styles/tags, entities decoded."""
    if not html:
        return ""
    parser = _TextParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # broken HTML: fall back to a blunt regex clean-up
        return _regex_strip(html)
    title = _collapse("".join(parser.title_parts))
    body = _collapse("".join(parser.parts))
    return _collapse(f"{title} {body}")


def _regex_strip(html: str) -> str:
    """Last-resort cleaner used only when the parser gives up."""
    cleaned = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    cleaned = re.sub(r"<(script|style|noscript|svg|template)\b.*?</\1\s*>", " ", cleaned, flags=re.S | re.I)
    cleaned = re.sub(r"<[^>]*>", " ", cleaned)
    return _collapse(_html.unescape(cleaned))


def _title_of(html: str) -> str:
    """The page <title>, or an empty string."""
    match = re.search(r"<title[^>]*>(.*?)</title\s*>", html or "", flags=re.S | re.I)
    return _collapse(_html.unescape(match.group(1))) if match else ""


# ---------------------------------------------------------------- URLs

def full_url(site_url: str, request_url: str) -> str:
    """Join the site link and a request path; a foreign host in request_url is dropped."""
    base = (site_url or "").strip().rstrip("/")
    raw = (request_url or "").strip()
    parts = urlsplit(raw)
    path = "/" + parts.path.lstrip("/")  # scheme/host (if any) are dropped
    query = f"?{parts.query}" if parts.query else ""
    return f"{base}{path}{query}"


def _path_of(request_url: str) -> str:
    """Just the path of a request URL (no query)."""
    return urlsplit((request_url or "").strip()).path


# ---------------------------------------------------------------- building replies

def _looks_blocked(status: int, body: str, is_json: bool) -> bool:
    """True for bot blocks: 403/429, or a challenge page behind a 503/200."""
    if status in (403, 429):
        return True
    if is_json:
        return False
    head = body[:5000].lower()
    if status == 503:
        return any(marker in head for marker in CHALLENGE_MARKERS)
    if status == 200:
        # Real shop pages often load a captcha script in <head>, so a 200 only counts as a block when it
        # is a short page carrying a real challenge marker.
        return len(body) < 50_000 and any(marker in head for marker in STRONG_CHALLENGE_MARKERS)
    return False


def _parse_json(resp: Any, body: str) -> Any | None:
    """Parse the body as JSON when the reply looks like JSON."""
    ctype = ""
    try:
        ctype = str(resp.headers.get("Content-Type", "") or "")
    except Exception:
        pass
    if "json" in ctype.lower() or body.lstrip()[:1] in ("{", "["):
        try:
            return _json.loads(body)
        except ValueError:
            return None
    return None


def _reply_from_response(device: str, url: str, resp: Any) -> SiteReply:
    """Build a SiteReply from a requests response."""
    body = resp.text or ""
    status = int(resp.status_code)
    data = _parse_json(resp, body)
    blocked = _looks_blocked(status, body, data is not None)
    if data is not None:
        text = _json.dumps(data, indent=2, ensure_ascii=False)
    else:
        text = strip_html(body)
    return SiteReply(
        device=device,
        url=url,
        status_code=status,
        blocked=blocked,
        text=text[:TEXT_CAP],
        json=data,
        html=body[:HTML_CAP],
    )


def _error_reply(device: str, url: str, message: str, status: int | None = None) -> SiteReply:
    return SiteReply(device=device, url=url, status_code=status, error=message)


# ---------------------------------------------------------------- Shopify cart

def _money(cents: Any, currency: str) -> str:
    """Shopify prices are in cents; show with a symbol for common currencies, else the code."""
    try:
        amount = f"{float(cents) / 100:.2f}"
    except (TypeError, ValueError):
        amount = "?"
    symbol = CURRENCY_SYMBOLS.get(currency.upper())
    if symbol:
        return f"{symbol}{amount}"
    return f"{currency} {amount}".strip()


def cart_summary(cart: Any) -> str:
    """One line describing a Shopify /cart.js reply."""
    if not isinstance(cart, dict):
        return "The cart could not be read."
    currency = str(cart.get("currency") or "")
    items = [i for i in (cart.get("items") or []) if isinstance(i, dict)]
    if not items:
        return "The cart is empty."
    total_count = cart.get("item_count")
    if not isinstance(total_count, int):
        total_count = sum(int(i.get("quantity") or 0) for i in items)
    lines = []
    for item in items:
        name = str(item.get("product_title") or item.get("title") or "item")
        variant = str(item.get("variant_title") or "")
        if variant and variant.lower() != "default title":
            name = f"{name} – {variant}"
        price = item.get("final_price", item.get("price"))
        lines.append(f"{item.get('quantity', 1)} × {name} ({_money(price, currency)})")
    noun = "item" if total_count == 1 else "items"
    total = _money(cart.get("total_price"), currency)
    return f"Cart has {total_count} {noun}: {', '.join(lines)}. Total {total}."


def _pick_variant(variants: list[Any], option: str) -> Any | None:
    """Choose a variant by option text, else first available, else first."""
    variants = [v for v in variants if isinstance(v, dict)]
    if not variants:
        return None
    wanted = (option or "").strip().lower()
    keys = ("option1", "option2", "option3", "title")
    if wanted:
        for v in variants:
            if any(str(v.get(k) or "").strip().lower() == wanted for k in keys):
                return v
        for v in variants:
            if any(wanted in str(v.get(k) or "").lower() for k in keys):
                return v
    for v in variants:
        if v.get("available"):
            return v
    return variants[0]


def _cart_items(request_body: Any) -> list[dict[str, Any]] | None:
    """The items of a cart-add body in any of the accepted forms, or None."""
    if not isinstance(request_body, dict):
        return None
    if isinstance(request_body.get("items"), list):
        items = [i for i in request_body["items"] if isinstance(i, dict)]
        return items or None
    if "id" in request_body or "handle" in request_body:
        return [request_body]
    return None


def _quantity(item: dict[str, Any]) -> int:
    try:
        return int(item.get("quantity", 1))
    except (TypeError, ValueError):
        return 1


def _shopify_cart_flow(
    session: requests.Session, base: str, device: str, url: str, request_body: Any
) -> SiteReply:
    """Add to cart the Shopify way, then read /cart.js. May raise requests exceptions."""
    items = _cart_items(request_body)
    if items is None:
        return _error_reply(device, url, "The cart request has no product in it.")
    lines: list[dict[str, Any]] = []
    for item in items:
        variant_id = item.get("id")
        handle = str(item.get("handle") or "").strip()
        if variant_id is None and handle:
            lookup_url = f"{base}/products/{handle}.json"
            resp = session.get(lookup_url, timeout=TIMEOUT)
            product = None
            if resp.status_code < 400:
                data = _parse_json(resp, resp.text or "")
                product = data.get("product") if isinstance(data, dict) else None
            variant = _pick_variant((product or {}).get("variants") or [], str(item.get("option") or ""))
            if variant is None or variant.get("id") is None:
                reply = _reply_from_response(device, url, resp)
                reply.url = url
                if not reply.blocked:
                    reply.error = f"We couldn't find the product '{handle}' on the site."
                return reply
            variant_id = variant["id"]
        if variant_id is None:
            return _error_reply(device, url, "The cart request has no product in it.")
        lines.append({"id": variant_id, "quantity": _quantity(item)})

    add = session.post(f"{base}/cart/add.js", json={"items": lines}, timeout=TIMEOUT)
    if add.status_code >= 400:
        return _reply_from_response(device, url, add)
    cart_resp = session.get(f"{base}/cart.js", timeout=TIMEOUT)
    reply = _reply_from_response(device, url, cart_resp)
    if reply.json is not None:
        reply.summary = cart_summary(reply.json)
    return reply


# ---------------------------------------------------------------- fetching

def fetch_pair(
    site_url: str, request_url: str, method: str, request_body: Any, device: str
) -> SiteReply:
    """Make the request as this device in a fresh session. Never raises."""
    url = full_url(site_url, request_url)
    base = (site_url or "").strip().rstrip("/")
    path = _path_of(request_url)
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": UA.get(device, UA["laptop"]),
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en",
            }
        )
        if (method or "GET").upper() == "POST":
            if ("/" + path.lstrip("/")).startswith("/cart/"):
                return _shopify_cart_flow(session, base, device, url, request_body)
            resp = session.post(url, json=request_body, timeout=TIMEOUT)
            return _reply_from_response(device, url, resp)
        resp = session.get(url, timeout=TIMEOUT)
        reply = _reply_from_response(device, url, resp)
        if path.rstrip("/").endswith("/cart.js") and reply.json is not None:
            reply.summary = cart_summary(reply.json)
        return reply
    except requests.Timeout:
        return _error_reply(device, url, TIMEOUT_MESSAGE)
    except requests.RequestException:
        return _error_reply(device, url, UNREACHABLE_MESSAGE)
    except Exception:  # never raise out of a fetch
        return _error_reply(device, url, UNREACHABLE_MESSAGE)


def fetch_home_text(site_url: str) -> str:
    """Readable text of the home page (as a laptop), up to 6000 chars; empty on failure."""
    reply = fetch_pair(site_url, "/", "GET", None, "laptop")
    if reply.error or reply.blocked or reply.status_code is None or reply.status_code >= 400:
        return ""
    return reply.text[:HOME_TEXT_CAP]


# ---------------------------------------------------------------- counting products

_HREF_RE = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
_PRODUCT_PATH_RE = re.compile(r"(?:^|/)products/([^/]+)/?$", re.I)


def _walk(data: Any, path: str) -> Any:
    """Follow a dotted path through dicts and lists; 'length' gives len(); None if missing."""
    current = data
    for part in path.split("."):
        if part == "length" and isinstance(current, (list, dict, str)):
            current = len(current)
        elif isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def count_products(reply: SiteReply) -> int:
    """Number of products: length of the JSON product list, else distinct /products/<handle> links."""
    if reply.json is not None:
        if isinstance(reply.json, list):
            return len(reply.json)
        for path in ("products", "items", "resources.results.products", "results"):
            found = _walk(reply.json, path)
            if isinstance(found, list):
                return len(found)
        return 0
    handles: set[str] = set()
    for match in _HREF_RE.finditer(reply.html or ""):
        href = _html.unescape(next(g for g in match.groups() if g is not None)).strip()
        found = _PRODUCT_PATH_RE.search(urlsplit(href).path)
        if not found:
            continue
        handle = found.group(1).lower()
        if handle.endswith((".json", ".js")) or not handle:
            continue
        handles.add(handle)
    return len(handles)


# ---------------------------------------------------------------- code checks

def _norm(text: str) -> str:
    return _collapse(text).lower()


def _not_set_up(why: str) -> tuple[bool, str]:
    return False, f"This check is not set up right: {why}"


def _status_words(code: int) -> str:
    try:
        phrase = HTTPStatus(code).phrase
    except ValueError:
        return str(code)
    return f"{code} ({'OK' if code == 200 else phrase.lower()})"


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _check_status(expected: str, reply: SiteReply) -> tuple[bool, str]:
    code = reply.status_code
    if code is None:
        return False, "The site did not answer."
    wanted = expected.strip()
    if not wanted:
        ok = 200 <= code < 400
        return ok, f"The page answered {_status_words(code)}."
    if not wanted.isdigit():
        return _not_set_up(f"'{wanted}' is not a status number.")
    ok = code == int(wanted)
    if ok:
        return True, f"The page answered {_status_words(code)}."
    return False, f"The page answered {_status_words(code)}, but {wanted} was expected."


def _check_count(expected: str, reply: SiteReply) -> tuple[bool, str]:
    if "=" not in expected:
        return _not_set_up("expected a value like item_count=1.")
    path, _, number = expected.rpartition("=")
    path, number = path.strip(), number.strip()
    try:
        want = float(number)
    except ValueError:
        return _not_set_up(f"'{number}' is not a number.")
    if not path:
        return _not_set_up("expected a value like item_count=1.")
    if reply.json is not None:
        who = "The cart" if reply.summary is not None else "The reply"
        value = _walk(reply.json, path)
        if value is None:
            return False, f"{who} has no '{path}' (expected {_num(want)})."
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return False, f"{who} shows '{path}' but it is not a number (expected {_num(want)})."
        try:
            got = float(value)
        except ValueError:
            return False, f"{who} shows '{path}' but it is not a number (expected {_num(want)})."
        return got == want, f"{who} shows {path} = {_num(got)} (expected {_num(want)})."
    got_n = _norm(reply.text).count(_norm(path))
    return got_n == want, f"'{path}' appears {got_n} time{'s' if got_n != 1 else ''} on the page (expected {_num(want)})."


def run_code_check(rule: str, expected: str | None, reply: SiteReply) -> tuple[bool, str]:
    """Decide a code rule. Returns (passed, plain-words detail)."""
    expected = (expected or "").strip()
    if rule == "status_ok":
        return _check_status(expected, reply)
    if rule in ("text_has", "text_absent"):
        if not expected:
            return _not_set_up("no word or phrase to look for.")
        found = _norm(expected) in _norm(reply.text)
        if rule == "text_has":
            return found, f"'{expected}' is on the page." if found else f"'{expected}' was not found on the page."
        return (not found), (
            f"'{expected}' is on the page, but it should not be." if found else f"'{expected}' is not on the page."
        )
    if rule == "count_equals":
        return _check_count(expected, reply)
    if rule == "min_results":
        try:
            needed = int(float(expected)) if expected else 1
        except ValueError:
            return _not_set_up(f"'{expected}' is not a number.")
        found_n = count_products(reply)
        noun = "product" if found_n == 1 else "products"
        return found_n >= needed, f"Found {found_n} {noun} (needed at least {needed})."
    raise ValueError(f"Not a code rule: {rule}")


# ---------------------------------------------------------------- excerpt

def _clip(text: str, limit: int = EXCERPT_CAP) -> str:
    text = _collapse(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def excerpt(reply: SiteReply, focus: list[str] | None = None) -> str:
    """Up to 500 chars of what the site said, on a single line."""
    if reply.error:
        return _clip(reply.error)
    if reply.blocked:
        if reply.status_code is not None:
            return _clip(f"The site blocked us (status {reply.status_code}).")
        return "The site blocked us."
    if reply.summary:
        return _clip(reply.summary)
    text = _collapse(reply.text)
    if not text:
        return "The site sent back an empty page."
    title = _title_of(reply.html)
    lowered = text.lower()
    hits = [(lowered.find(w.strip().lower()), w) for w in (focus or []) if w and w.strip()]
    hits = [(pos, w) for pos, w in hits if pos >= 0]
    if hits:
        pos, word = min(hits)
        start = max(0, pos - 100)
        end = min(len(text), pos + len(word.strip()) + 100)
        snippet = ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
        return _clip(f"{title} — {snippet}" if title else snippet)
    return _clip(text)
