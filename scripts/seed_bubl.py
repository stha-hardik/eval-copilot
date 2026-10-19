"""Enter Brajesh's 10 golden pairs for Bubl Solar through the app's own doors (milestone M3).

Usage (password only in the shell, never in a file):
    EC_EMAIL=you@example.com EC_PASSWORD='...' python3 scripts/seed_bubl.py https://<your-app>.vercel.app

What it does:
1. Reads bublsolar.com's public product and collection lists to find the real Solaris, Walkie and
   Cabinet Lights links (Shopify's /products.json and /collections.json).
2. Logs in (or signs up) through /api/login, creates the "Bubl Solar" project through /api/projects.
3. For each pair: asks Tidy with AI (/api/pairs/tidy) to propose the checks, puts in the real link
   found in step 1, and saves it approved through /api/projects/{id}/pairs. Pair #8 is priority.
Running it twice does not add the pairs twice.
"""
import json
import os
import sys

import requests

SITE = "https://bublsolar.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

PAIRS = [
    ("Opens bublsolar.com and browses the menu.",
     "Can easily find the product categories, search and cart. Nothing overlaps or blocks the buttons on mobile."),
    ('Searches "Solaris".',
     "Solaris appears in the results, and clicking it opens the correct product page."),
    ('Searches "lamp for balcony".',
     "Shows at least one suitable lamp, such as Solaris, rather than no results or unrelated products."),
    ('Opens "Cabinet Lights" from the menu.',
     "Sees relevant products such as Walkie, Walkie X and Comfort, with working images, prices and product links."),
    ("Opens Solaris to understand whether it suits their needs.",
     "Can easily find its dimensions, brightness, charging options, charging time, battery runtime and warranty. "
     "Information is consistent across the page."),
    ("Changes the Solaris colour from Black to Sand or Rust Red.",
     "The selected colour is clear, the main image matches it, and any price or availability change is shown "
     "before adding it."),
    ('Uses the "Turn On" preview and browses product photos.',
     "The preview shows the lamp illuminated, photos load correctly, and the customer can close the enlarged "
     "view easily."),
    ('Starts with an empty cart, selects one Solaris and clicks "Add to cart" once.',
     "Exactly one lamp in the selected colour is added. The cart does not unexpectedly contain five lamps or "
     "extra products."),
    ("Adds one Solaris and one Walkie, then refreshes the page.",
     "Both products remain in the cart with the correct options and quantities, without duplicates or missing "
     "items."),
    ("Checks the final order summary before payment.",
     "Products, colours, quantities and discounts match the cart. Shipping charges and the final payable amount "
     "are clearly shown, with no unexplained extras. Any free-shipping promise is honoured."),
]


def site_json(path: str):
    r = requests.get(SITE + path, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=20)
    r.raise_for_status()
    return r.json()


def find_handles() -> dict:
    """The real Shopify handles, read from the live store."""
    products = site_json("/products.json?limit=250").get("products", [])
    collections = site_json("/collections.json?limit=250").get("collections", [])

    def product(*words, exclude=()):
        for p in products:
            title = p["title"].lower()
            if all(w in title for w in words) and not any(x in title for x in exclude):
                return p
        return None

    solaris = product("solaris")
    walkie = product("walkie", exclude=("x",)) or product("walkie")
    cabinet = next((c for c in collections if "cabinet" in c["title"].lower()), None)
    if not solaris or not walkie or not cabinet:
        sys.exit(f"Couldn't find all handles: solaris={bool(solaris)} walkie={bool(walkie)} cabinet={bool(cabinet)}")
    colours = sorted({v.get("option1") for v in solaris.get("variants", []) if v.get("option1")})
    found = {"solaris": solaris["handle"], "walkie": walkie["handle"], "cabinet": cabinet["handle"],
             "solaris_colours": colours}
    print("Found on bublsolar.com:", json.dumps(found))
    return found


def requests_for(h: dict) -> list[tuple[str, str, dict | None]]:
    black = next((c for c in h["solaris_colours"] if "black" in c.lower()), None)
    sol, walk = h["solaris"], h["walkie"]
    return [
        ("/", "GET", None),
        ("/search?q=Solaris", "GET", None),
        ("/search?q=lamp+for+balcony", "GET", None),
        (f"/collections/{h['cabinet']}", "GET", None),
        (f"/products/{sol}", "GET", None),
        (f"/products/{sol}", "GET", None),
        (f"/products/{sol}", "GET", None),
        ("/cart/add.js", "POST", {"items": [{"handle": sol, "option": black, "quantity": 1}]}),
        ("/cart/add.js", "POST", {"items": [{"handle": sol, "option": black, "quantity": 1},
                                            {"handle": walk, "option": None, "quantity": 1}]}),
        ("/cart/add.js", "POST", {"items": [{"handle": sol, "option": black, "quantity": 1}]}),
    ]


# Checks that code can decide exactly, added when Tidy with AI didn't propose them.
MUST_HAVE = {
    2: [{"decided_by": "code", "rule": "text_has", "expected": "Solaris"},
        {"decided_by": "code", "rule": "min_results", "expected": "1"}],
    3: [{"decided_by": "code", "rule": "min_results", "expected": "1"}],
    8: [{"decided_by": "code", "rule": "count_equals", "expected": "item_count=1"}],
    9: [{"decided_by": "code", "rule": "count_equals", "expected": "item_count=2"},
        {"decided_by": "code", "rule": "count_equals", "expected": "items.length=2"}],
}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    base = sys.argv[1].rstrip("/")
    email, password = os.environ.get("EC_EMAIL"), os.environ.get("EC_PASSWORD")
    if not email or not password:
        sys.exit("Set EC_EMAIL and EC_PASSWORD in the shell first.")
    handles = find_handles()

    s = requests.post(f"{base}/api/login", json={"email": email, "password": password}, timeout=30)
    if s.status_code == 401:
        s = requests.post(f"{base}/api/signup", json={"email": email, "password": password}, timeout=30)
    s.raise_for_status()
    auth = {"Authorization": "Bearer " + s.json()["access_token"]}

    def api(method, path, body=None):
        r = requests.request(method, base + path, json=body, headers=auth, timeout=60)
        if r.status_code >= 400:
            sys.exit(f"{method} {path} -> {r.status_code} {r.text}")
        return r.json()

    project = next((p for p in api("GET", "/api/projects")["projects"] if p["name"] == "Bubl Solar"), None)
    pid = project["id"] if project else api("POST", "/api/projects", {"name": "Bubl Solar", "site_url": SITE})["id"]
    existing = {p["user_does"] for p in api("GET", f"/api/projects/{pid}")["pairs"]}

    for n, ((does, good), (url, method, body)) in enumerate(zip(PAIRS, requests_for(handles)), start=1):
        if does in existing:
            print(f"#{n} already there")
            continue
        draft = api("POST", "/api/pairs/tidy",
                    {"rough_text": f"User does: {does}\nGood result: {good}\nPage: {url}", "site_url": SITE})["pair"]
        checks = draft["checks"]
        for extra in MUST_HAVE.get(n, []):
            if not any(c["rule"] == extra["rule"] and c["expected"] == extra["expected"] for c in checks):
                checks.append(extra)
        pair = {"user_does": does, "good_result": good, "request_url": url, "method": method,
                "request_body": body, "source": "builder", "approved": True, "is_priority": n == 8,
                "checks": checks[:8]}
        saved = api("POST", f"/api/projects/{pid}/pairs", pair)
        print(f"#{n} saved {saved['id']} with {len(checks[:8])} checks: "
              + ", ".join(f"{c['rule']}({c['expected'] or ''})" for c in checks[:8]))
    print(f"Done. Project: {base}/project.html?id={pid}")


if __name__ == "__main__":
    main()
