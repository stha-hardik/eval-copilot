"""Tests for api/_lib/site.py. No network: requests.Session.get/post are replaced."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api._lib import site  # noqa: E402
from api._lib.site import SiteReply  # noqa: E402

SITE = "https://shop.example.com"


class FakeResp:
    def __init__(self, status=200, body="", ctype="text/html"):
        self.status_code = status
        self.text = body if isinstance(body, str) else json.dumps(body)
        self.headers = {"Content-Type": "application/json" if not isinstance(body, str) else ctype}


class FakeNet:
    """Routes fake GET/POST calls by URL and records them."""

    def __init__(self, gets=None, posts=None):
        self.gets, self.posts = gets or {}, posts or {}
        self.calls = []

    def _answer(self, table, url):
        answer = table[url]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def get(self, session, url, **kw):
        self.calls.append(("GET", url, kw, dict(session.headers)))
        return self._answer(self.gets, url)

    def post(self, session, url, **kw):
        self.calls.append(("POST", url, kw, dict(session.headers)))
        return self._answer(self.posts, url)


def patched(net):
    """Patch Session.get/post with plain functions so they receive the session as `self`."""
    return (
        patch.object(requests.Session, "get", lambda self, url, **kw: net.get(self, url, **kw)),
        patch.object(requests.Session, "post", lambda self, url, **kw: net.post(self, url, **kw)),
    )


def run(net, *args):
    get_patch, post_patch = patched(net)
    with get_patch, post_patch:
        return site.fetch_pair(*args)


# ---------------------------------------------------------------- strip_html / full_url

def test_strip_html():
    html = (
        "<html><head><style>a{}</style><title>Solaris &amp; Co</title><script>var x=1;</script></head>"
        "<body><!-- hidden --><noscript>enable js</noscript><svg><path d='x'/></svg>"
        "<template><p>tpl</p></template><h1>Hello &lt;b&gt;</h1><p>Big\n\n  sale</p><div>Tom &eacute;</div></body>"
    )
    text = site.strip_html(html)
    assert text.startswith("Solaris & Co")
    for gone in ("var x", "a{}", "hidden", "enable js", "tpl", "<p>"):
        assert gone not in text
    assert "Hello <b>" in text and "Big sale" in text and "Tom é" in text


def test_strip_html_broken():
    assert "ok" in site.strip_html("<div><p>ok<b>unclosed <i>stuff")
    assert site.strip_html("") == ""


def test_full_url():
    assert site.full_url("https://a.com/", "/search?q=x") == "https://a.com/search?q=x"
    assert site.full_url("https://a.com//", "/cart.js") == "https://a.com/cart.js"
    assert site.full_url("https://a.com", "products/x") == "https://a.com/products/x"
    assert site.full_url("https://a.com", "https://evil.com/p?a=1") == "https://a.com/p?a=1"
    assert site.full_url("https://a.com", "//evil.com/p") == "https://a.com/p"


# ---------------------------------------------------------------- GET basics

def test_get_ok_and_headers():
    net = FakeNet(gets={f"{SITE}/": FakeResp(200, "<title>Home</title><p>Welcome</p>")})
    reply = run(net, SITE, "/", "GET", None, "phone")
    assert reply.status_code == 200 and not reply.blocked and reply.error is None
    assert reply.text == "Home Welcome" and "<p>" in reply.html
    headers = net.calls[0][3]
    assert "iPhone" in headers["User-Agent"] and headers["Accept-Language"] == "en"
    assert net.calls[0][2]["timeout"] == site.TIMEOUT


def test_403_blocked():
    net = FakeNet(gets={f"{SITE}/": FakeResp(403, "Forbidden")})
    reply = run(net, SITE, "/", "GET", None, "laptop")
    assert reply.blocked and reply.status_code == 403
    assert site.excerpt(reply) == "The site blocked us (status 403)."


def test_challenge_page_blocked():
    net = FakeNet(gets={f"{SITE}/": FakeResp(503, "<title>Just a moment...</title>")})
    assert run(net, SITE, "/", "GET", None, "laptop").blocked
    net = FakeNet(gets={f"{SITE}/": FakeResp(200, "<html><title>Just a moment...</title>cf-chl</html>")})
    assert run(net, SITE, "/", "GET", None, "laptop").blocked
    # A real shop page that loads a captcha script is not a block.
    net = FakeNet(gets={f"{SITE}/": FakeResp(200, "<html><script src='hcaptcha.js'></script>Solaris lamp</html>")})
    assert not run(net, SITE, "/", "GET", None, "laptop").blocked
    net = FakeNet(gets={f"{SITE}/": FakeResp(404, "<p>Access denied</p>")})
    assert not run(net, SITE, "/", "GET", None, "laptop").blocked


def test_timeout_and_connection_errors():
    net = FakeNet(gets={f"{SITE}/": requests.Timeout()})
    reply = run(net, SITE, "/", "GET", None, "phone")
    assert reply.status_code is None and "too long" in reply.error
    net = FakeNet(gets={f"{SITE}/": requests.ConnectionError()})
    reply = run(net, SITE, "/", "GET", None, "phone")
    assert reply.status_code is None and reply.error == "We couldn't reach the site."
    assert site.excerpt(reply) == "We couldn't reach the site."


def test_fetch_home_text():
    net = FakeNet(gets={f"{SITE}/": FakeResp(200, "<p>" + "word " * 3000 + "</p>")})
    with patched(net)[0]:
        assert len(site.fetch_home_text(SITE)) <= 6000
    net = FakeNet(gets={f"{SITE}/": requests.Timeout()})
    with patched(net)[0]:
        assert site.fetch_home_text(SITE) == ""


# ---------------------------------------------------------------- Shopify cart

PRODUCT = {
    "product": {
        "variants": [
            {"id": 111, "title": "Black", "option1": "Black", "available": True},
            {"id": 222, "title": "Sand", "option1": "Sand", "available": True},
        ]
    }
}
CART = {
    "item_count": 1,
    "currency": "EUR",
    "total_price": 5900,
    "items": [
        {"quantity": 1, "product_title": "Solaris", "variant_title": "Sand", "final_price": 5900, "price": 5900}
    ],
}


def cart_net(add_status=200):
    return FakeNet(
        gets={
            f"{SITE}/products/solaris.json": FakeResp(200, PRODUCT),
            f"{SITE}/cart.js": FakeResp(200, CART),
        },
        posts={f"{SITE}/cart/add.js": FakeResp(add_status, {"items": []})},
    )


def test_shopify_cart_flow():
    net = cart_net()
    body = {"items": [{"handle": "solaris", "option": "sand", "quantity": 1}]}
    reply = run(net, SITE, "/cart/add.js", "POST", body, "laptop")
    posts = [c for c in net.calls if c[0] == "POST"]
    assert len(posts) == 1 and posts[0][2]["json"] == {"items": [{"id": 222, "quantity": 1}]}
    assert [c[1] for c in net.calls] == [
        f"{SITE}/products/solaris.json",
        f"{SITE}/cart/add.js",
        f"{SITE}/cart.js",
    ]
    assert reply.json == CART
    assert reply.summary == "Cart has 1 item: 1 × Solaris – Sand (€59.00). Total €59.00."
    assert site.excerpt(reply) == reply.summary
    assert site.run_code_check("count_equals", "item_count=1", reply)[0] is True
    passed, detail = site.run_code_check("count_equals", "items.length=2", reply)
    assert passed is False and detail == "The cart shows items.length = 1 (expected 2)."
    assert site.run_code_check("count_equals", "items.0.quantity = 1", reply)[0] is True
    passed, detail = site.run_code_check("count_equals", "item_count=5", reply)
    assert detail == "The cart shows item_count = 1 (expected 5)."


def test_shopify_plain_id_body_skips_lookup():
    net = cart_net()
    reply = run(net, SITE, "/cart/add.js", "POST", {"id": 111, "quantity": 2}, "phone")
    assert net.calls[0][2]["json"] == {"items": [{"id": 111, "quantity": 2}]}
    assert reply.summary.startswith("Cart has 1 item")


def test_variant_fallbacks():
    variants = [{"id": 1, "title": "A", "available": False}, {"id": 2, "title": "B", "available": True}]
    assert site._pick_variant(variants, "zzz")["id"] == 2
    assert site._pick_variant(variants[:1], "")["id"] == 1
    assert site._pick_variant([{"id": 3, "option2": "Extra Large"}], "large")["id"] == 3


def test_product_404():
    net = FakeNet(gets={f"{SITE}/products/nope.json": FakeResp(404, "Not found")})
    body = {"items": [{"handle": "nope", "quantity": 1}]}
    reply = run(net, SITE, "/cart/add.js", "POST", body, "laptop")
    assert reply.status_code == 404
    assert reply.error == "We couldn't find the product 'nope' on the site."
    assert not any(c[0] == "POST" for c in net.calls)


def test_add_failure_keeps_response():
    err = {"status": 422, "description": "All 1 Solaris are in your cart."}
    net = FakeNet(
        gets={f"{SITE}/products/solaris.json": FakeResp(200, PRODUCT)},
        posts={f"{SITE}/cart/add.js": FakeResp(422, err)},
    )
    reply = run(net, SITE, "/cart/add.js", "POST", {"items": [{"handle": "solaris", "quantity": 1}]}, "laptop")
    assert reply.status_code == 422 and "All 1 Solaris" in reply.text and reply.error is None


def test_get_cart_js_has_summary_and_other_post():
    net = FakeNet(gets={f"{SITE}/cart.js": FakeResp(200, CART)})
    assert run(net, SITE, "/cart.js", "GET", None, "laptop").summary.startswith("Cart has 1 item")
    net = FakeNet(posts={f"{SITE}/api/x": FakeResp(200, {"ok": True})})
    reply = run(net, SITE, "/api/x", "POST", {"a": 1}, "laptop")
    assert net.calls[0][2]["json"] == {"a": 1} and reply.json == {"ok": True}


def test_cart_summary_currency():
    cart = {"item_count": 2, "currency": "CHF", "total_price": 10000, "items": [
        {"quantity": 2, "title": "Mug", "variant_title": "Default Title", "price": 5000}]}
    assert site.cart_summary(cart) == "Cart has 2 items: 2 × Mug (CHF 50.00). Total CHF 100.00."


# ---------------------------------------------------------------- checks

LISTING = (
    '<a href="/products/solaris">A</a><a href="/products/solaris?variant=1">dup</a>'
    "<a href='https://shop.example.com/products/luna/'>B</a><a href=\"/products/vega\">C</a>"
    '<a href="/products/vega.json">json</a><a href="/collections/all">no</a>'
)


def test_min_results_html():
    reply = SiteReply(device="phone", url="u", status_code=200, html=LISTING)
    assert site.count_products(reply) == 3
    assert site.run_code_check("min_results", "3", reply) == (True, "Found 3 products (needed at least 3).")
    passed, detail = site.run_code_check("min_results", "", reply)
    assert passed and detail == "Found 3 products (needed at least 1)."
    assert site.run_code_check("min_results", "4", reply)[0] is False


def test_min_results_json():
    reply = SiteReply(device="p", url="u", status_code=200, json={"resources": {"results": {"products": [1, 2]}}})
    assert site.count_products(reply) == 2
    reply.json = {"products": [1, 2, 3, 4]}
    assert site.count_products(reply) == 4
    reply.json = {"nothing": 1}
    assert site.count_products(reply) == 0


def test_text_checks():
    reply = SiteReply(device="p", url="u", status_code=200, text="Meet   the SOLARIS lamp")
    assert site.run_code_check("text_has", "solaris  LAMP", reply) == (True, "'solaris  LAMP' is on the page.")
    assert site.run_code_check("text_has", "Luna", reply) == (False, "'Luna' was not found on the page.")
    assert site.run_code_check("text_absent", "Luna", reply)[0] is True
    assert site.run_code_check("text_absent", "Solaris", reply)[0] is False


def test_count_equals_on_text_and_bad_expected():
    reply = SiteReply(device="p", url="u", status_code=200, text="sale sale sale")
    assert site.run_code_check("count_equals", "sale = 3", reply)[0] is True
    passed, detail = site.run_code_check("count_equals", "nonsense", reply)
    assert not passed and detail.startswith("This check is not set up right")


def test_status_ok():
    ok = SiteReply(device="p", url="u", status_code=200)
    missing = SiteReply(device="p", url="u", status_code=404)
    assert site.run_code_check("status_ok", "", ok) == (True, "The page answered 200 (OK).")
    assert site.run_code_check("status_ok", None, missing) == (False, "The page answered 404 (not found).")
    assert site.run_code_check("status_ok", "404", missing)[0] is True
    assert site.run_code_check("status_ok", "200", missing)[0] is False
    assert site.run_code_check("status_ok", "", SiteReply(device="p", url="u"))[0] is False


def test_unknown_rule_raises():
    with pytest.raises(ValueError):
        site.run_code_check("ai_judge", "q", SiteReply(device="p", url="u"))


# ---------------------------------------------------------------- excerpt

def test_excerpt():
    html = "<title>My Shop</title><p>" + "intro " * 300 + "the Solaris lamp is great " + "tail " * 300 + "</p>"
    reply = SiteReply(device="p", url="u", status_code=200, html=html, text=site.strip_html(html))
    plain = site.excerpt(reply)
    assert len(plain) <= 500 and "\n" not in plain and plain.startswith("My Shop")
    hit = site.excerpt(reply, ["solaris"])
    assert hit.startswith("My Shop") and "Solaris lamp" in hit and len(hit) <= 500
    assert "Solaris" not in site.excerpt(reply, ["nothere"])
    long_err = SiteReply(device="p", url="u", error="x" * 900)
    assert len(site.excerpt(long_err)) <= 500
