"""End-to-end check of the live app, through the same doors the browser uses.

Usage (passwords only in the shell, never in a file):
    EC_EMAIL=you@example.com EC_PASSWORD='...' python3 scripts/smoke_live.py https://<your-app>.vercel.app

1. M1: /api/health answers ok.
2. M2: two throwaway accounts (tester.a+eval / tester.b+eval @example.com, random passwords): A creates a
   project; B gets an empty list and a 404 for A's project.
3. M4: logged in as EC_EMAIL, runs every approved pair of "Bubl Solar" (door 8, then door 9 once per pair,
   then door 10) and prints pass / fail / can't test counts and the 3 worst fails.
4. M5: re-runs 2 pairs as "changed", checks Run 1's rows are untouched, and prints the comparison.
"""
import json
import os
import secrets
import sys
from collections import Counter

import requests


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    base = sys.argv[1].rstrip("/")

    def call(method, path, body=None, token=None, ok=(200, 201)):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = requests.request(method, base + path, json=body, headers=headers, timeout=70)
        if ok and r.status_code not in ok:
            sys.exit(f"FAILED {method} {path} -> {r.status_code} {r.text[:300]}")
        return r

    def account(email):
        password = secrets.token_urlsafe(18)
        r = call("POST", "/api/signup", {"email": email, "password": password}, ok=None)
        if r.status_code == 400:  # already exists from an earlier smoke run: make a fresh address
            email = email.replace("+eval", f"+eval{secrets.randbelow(10**6)}")
            r = call("POST", "/api/signup", {"email": email, "password": password}, ok=None)
        if r.status_code == 409:
            sys.exit("Sign-up still asks for email confirmation: turn off 'Confirm email' in Supabase.")
        if r.status_code != 200:
            sys.exit(f"FAILED signup {email} -> {r.status_code} {r.text[:200]}")
        return email, r.json()["access_token"]

    print("M1 health:", call("GET", "/api/health").json())

    a_email, a = account("tester.a+eval@example.com")
    b_email, b = account("tester.b+eval@example.com")
    pid = call("POST", "/api/projects", {"name": "A's test site", "site_url": "https://example.com"}, a).json()["id"]
    b_list = call("GET", "/api/projects", token=b).json()["projects"]
    b_get = call("GET", f"/api/projects/{pid}", token=b, ok=None).status_code
    a_list = call("GET", "/api/projects", token=a).json()["projects"]
    print(f"M2 RLS: A={a_email} sees {len(a_list)} project(s); B={b_email} sees {len(b_list)}; "
          f"B asking for A's project by id -> {b_get}")
    if b_list or b_get != 404:
        sys.exit("RLS FAILED")

    email, password = os.environ.get("EC_EMAIL"), os.environ.get("EC_PASSWORD")
    if not email or not password:
        sys.exit("Set EC_EMAIL and EC_PASSWORD to run M4/M5 as the builder.")
    me = call("POST", "/api/login", {"email": email, "password": password}).json()["access_token"]
    project = next((p for p in call("GET", "/api/projects", token=me).json()["projects"]
                    if p["name"] == "Bubl Solar"), None)
    if not project:
        sys.exit("No 'Bubl Solar' project yet: run scripts/seed_bubl.py first.")

    def run(kind, pair_ids=None, note=""):
        body = {"kind": kind} if kind == "full" else {"kind": kind, "pair_ids": pair_ids, "other_changes": note}
        started = call("POST", f"/api/projects/{project['id']}/runs", body, me).json()
        rid = started["run"]["id"]
        for pair_id in started["pair_ids"]:
            call("POST", f"/api/runs/{rid}/pairs/{pair_id}", token=me)
        call("POST", f"/api/runs/{rid}/finish", token=me)
        return call("GET", f"/api/runs/{rid}", token=me).json()

    run1 = run("full")
    counts = Counter(r["outcome"] for r in run1["rows"])
    print(f"M4 Run {run1['run']['run_number']}: {len(run1['rows'])} rows · pass {counts['pass']} · "
          f"fail {counts['fail']} · can't test {counts['cant_test']}")
    assert all(r["outcome"] in ("pass", "fail", "cant_test") for r in run1["rows"])
    manual = sum(1 for r in run1["rows"] for c in r["checks"] if c["rule"] == "manual" and c["passed"] is None)
    print(f"   manual checks waiting for 'Looks right / Looks wrong': {manual}")
    for r in run1["rows"]:
        print(f"   #{r['position']:>2} {r['device']:<6} {r['outcome']:<9} {r['status_code']} {r['why'][:110]}")
    print("   3 key points:")
    for p in run1["points"]:
        print(f"   {p['rank']}. #{p['position']} {p['device']}: {p['explanation']}")

    tick = list(dict.fromkeys(r["pair_id"] for r in run1["rows"]))[:2]
    run2 = run("changed", tick, "Smoke test: re-running two pairs")
    again = call("GET", f"/api/runs/{run1['run']['id']}", token=me).json()
    same = [(r["result_id"], r["outcome"]) for r in again["rows"]] == [(r["result_id"], r["outcome"]) for r in run1["rows"]]
    print(f"M5 Run {run2['run']['run_number']} (changed): {len(run2['rows'])} rows; Run 1 untouched: {same}")
    for c in run2["changed"]:
        print(f"   #{c['position']} good now? {c['good_now']} (phone {c['phone']}, laptop {c['laptop']})")
    cmp = call("GET", f"/api/runs/{run2['run']['id']}/compare?with={run1['run']['id']}", token=me).json()
    print("   compare:", json.dumps(Counter(r["verdict"] for r in cmp["rows"])))
    if not same:
        sys.exit("Run 1 changed: FAILED")
    print(f"Results pages: {base}/run.html?id={run1['run']['id']}  and  {base}/run.html?id={run2['run']['id']}")


if __name__ == "__main__":
    main()
