"""Temporary M7 helper: explore bublsolar.com in a local browser to write real click steps."""
import json
from playwright.sync_api import sync_playwright

SITE = "https://bublsolar.com"
PHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

CLICKABLES = """() => [...document.querySelectorAll('a,button,label,summary,[role=button],input[type=radio],input[type=submit]')]
  .filter(e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
                 return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; })
  .map(e => ({tag: e.tagName.toLowerCase(), text: (e.innerText || e.value || '').trim().replace(/\\s+/g,' ').slice(0,60),
              aria: e.getAttribute('aria-label'), name: e.getAttribute('name'), cls: (e.className||'').toString().slice(0,60),
              href: e.getAttribute('href'), y: Math.round(e.getBoundingClientRect().top)}))
  .filter(x => x.text || x.aria).slice(0, 80)"""

with sync_playwright() as p:
    b = p.chromium.launch()
    for label, ctx_args, path in [
        ("PHONE HOME", dict(viewport={"width": 390, "height": 844}, user_agent=PHONE_UA, is_mobile=True), "/"),
        ("LAPTOP PRODUCT", dict(viewport={"width": 1440, "height": 900}), "/products/solaris"),
    ]:
        ctx = b.new_context(**ctx_args)
        page = ctx.new_page()
        page.goto(SITE + path, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        print(f"===== {label} {page.url} title={page.title()!r} text_len={len(page.inner_text('body'))}")
        for x in page.evaluate(CLICKABLES):
            print(json.dumps(x))
        ctx.close()

    # Try the add-to-cart flow once, report the cart, and look at /cart and the Turn On element.
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(SITE + "/products/solaris", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)
    for sel in ["text=Turn On", "text=Sand", "text=Rust Red", "button[name=add]", "text=Add to cart"]:
        loc = page.locator(sel)
        print(f"SELECTOR {sel!r}: count={loc.count()} visible_first={loc.first.is_visible() if loc.count() else None}")
    page.locator("text=Sand").first.click(timeout=5000)
    page.wait_for_timeout(1500)
    print("AFTER SAND url:", page.url)
    page.locator("button[name=add]").first.click(timeout=5000)
    page.wait_for_timeout(3000)
    cart = page.evaluate("() => fetch('/cart.js').then(r => r.json())")
    print("CART after 1 click:", json.dumps({"item_count": cart["item_count"],
          "items": [(i["product_title"], i.get("variant_title"), i["quantity"]) for i in cart["items"]]}))
    page.goto(SITE + "/cart", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    print("CART PAGE text:", page.inner_text("body")[:800].replace("\n", " | "))
    for x in page.evaluate(CLICKABLES):
        if "check" in (x["text"] or "").lower() or "check" in (x["name"] or "").lower():
            print("CHECKOUT-ish:", json.dumps(x))
    ctx.close()
    b.close()
