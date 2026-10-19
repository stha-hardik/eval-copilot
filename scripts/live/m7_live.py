"""Temporary M7 live test: drives the LIVE app's own doors from a GitHub runner (open internet).

It signs up a throwaway test account (random password, never printed), copies the owner's 10 Bubl Solar pairs
exactly as they are in the database (scripts/live/bubl_pairs.json), runs them all, re-runs #8, and checks
the routing rules: the real browser only on #1, #6, #7, #8, #10; everything else a plain page read.
"""
import json
import os
import secrets
import sys
import time
from collections import Counter
from pathlib import Path

import requests

BASE = os.environ.get("APP", "https://eval-copilot.vercel.app")
BROWSER_PAIRS = {1, 6, 7, 8, 10}
s = requests.Session()


def call(method, path, body=None, ok=(200, 201)):
    t = time.time()
    r = s.request(method, BASE + path, json=body, timeout=170)
    if r.status_code not in ok:
        sys.exit(f"FAILED {method} {path} -> {r.status_code} {r.text[:300]}")
    return r.json(), time.time() - t


health, _ = call("GET", "/api/health")
print("health:", health)
if not health.get("browser"):
    sys.exit("The live app has no Browserless token (health.browser is false); stopping before any run.")

email = f"tester.m7+{secrets.token_hex(4)}@example.com"
session, _ = call("POST", "/api/signup", {"email": email, "password": secrets.token_urlsafe(18)})
s.headers["Authorization"] = "Bearer " + session["access_token"]
print("test account:", email)

pid = call("POST", "/api/projects", {"name": "Bubl Solar (M7 live test copy)", "site_url": "https://bublsolar.com"})[0]["id"]
pairs = json.loads(Path(__file__).with_name("bubl_pairs.json").read_text())
by_id = {}
for p in pairs:
    saved, _ = call("POST", f"/api/projects/{pid}/pairs", {
        "user_does": p["user_does"], "good_result": p["good_result"], "request_url": p["request_url"],
        "method": p["method"], "request_body": p["request_body"], "source": "builder",
        "approved": True, "is_priority": p["is_priority"],
        "checks": [{"rule": c["rule"], "expected": c["expected"], "steps": c["steps"]} for c in p["checks"]]})
    by_id[saved["id"]] = p["position"]
print(f"copied {len(by_id)} pairs")


def run(kind, pair_ids=None):
    body = {"kind": "full"} if kind == "full" else {"kind": "changed", "pair_ids": pair_ids, "other_changes": ""}
    started, _ = call("POST", f"/api/projects/{pid}/runs", body)
    rid = started["run"]["id"]
    timings = {}
    for pair_id in started["pair_ids"]:
        out, secs = call("POST", f"/api/runs/{rid}/pairs/{pair_id}")
        timings[by_id[pair_id]] = round(secs, 1)
        for r in out["rows"]:
            print(f"  #{r['position']:>2} {r['device']:<6} via={r['via']:<7} {r['outcome']:<9} ({secs:5.1f}s) "
                  f"{(r['human_reason'] or r['why'] or '')[:90]}")
            for c in r["checks"]:
                if c["rule"] in ("ai_vision", "browser_count"):
                    print(f"        {c['rule']:<13} passed={c['passed']!s:<5} {str(c['why'])[:110]}")
            if r["via"] != "fetch":
                print(f"        said: {r['what_site_said'][:160]}")
    fin, _ = call("POST", f"/api/runs/{rid}/finish")
    full, _ = call("GET", f"/api/runs/{rid}")
    return rid, full, fin, timings


print("\n== Run 1: all pairs")
rid1, run1, fin1, t1 = run("full")
rows = run1["rows"]
c = Counter(r["outcome"] for r in rows)
vias = Counter(r["via"] for r in rows)
print(f"Run 1: {len(rows)} rows · pass {c['pass']} · fail {c['fail']} · can't test {c['cant_test']} · via {dict(vias)}")
print("door 9 seconds per pair:", t1)
for p in fin1["points"]:
    print(f"  worst {p['rank']}: #{p['position']} {p['device']}: {p['explanation'][:160]}")
non_fetch = {r["position"] for r in rows if r["via"] != "fetch"}
problems = []
if non_fetch != BROWSER_PAIRS:
    problems.append(f"browser/human pairs were {sorted(non_fetch)}, expected {sorted(BROWSER_PAIRS)}")
eight = [r for r in rows if r["position"] == 8]
if not all(r["via"] == "browser" for r in eight):
    problems.append("#8 did not use the real browser on both devices")
for r in eight:
    for chk in r["checks"]:
        if chk["rule"] == "browser_count" and chk["passed"] is not True:
            problems.append(f"#8 {r['device']} browser_count: {chk['why']}")
ten = [r for r in rows if r["position"] == 10]
for r in ten:
    if r["outcome"] == "fail" and r["via"] == "human":
        problems.append("#10 handed to a person but marked fail")
sessions1 = sum(1 for r in rows if r["via"] != "fetch")

print("\n== Run 2: re-run changed, #8 only")
eight_id = next(k for k, v in by_id.items() if v == 8)
before = [(r["result_id"], r["outcome"], r["via"]) for r in rows]
rid2, run2, fin2, t2 = run("changed", [eight_id])
sessions2 = sum(1 for r in run2["rows"] if r["via"] != "fetch")
after = [(r["result_id"], r["outcome"], r["via"]) for r in call("GET", f"/api/runs/{rid1}")[0]["rows"]]
print(f"Run 2: {len(run2['rows'])} rows, browser sessions {sessions2}; Run 1 untouched: {before == after}")
for ch in run2["changed"]:
    print(f"  #{ch['position']} good now? {ch['good_now']} (phone {ch['phone']}, laptop {ch['laptop']})")
if before != after:
    problems.append("Run 1 changed after the re-run")
if sessions2 not in (1, 2):
    problems.append(f"re-run used {sessions2} browser sessions")

print(f"\nBrowser sessions: Run 1 {sessions1}, Run 2 {sessions2} (each under 30 s = 1 Browserless unit)")
print("RESULT:", "PASS" if not problems else "PROBLEMS")
for p in problems:
    print("  -", p)
sys.exit(1 if problems else 0)
