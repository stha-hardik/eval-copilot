"""The real browser: one Browserless session per pair + device, driven from Python with plain `requests`.

Browserless (https://docs.browserless.io/rest-apis/function) runs `browser_fn.mjs` (Puppeteer) on its own
hosted Chrome, so nothing is installed or launched on Vercel. Every way it can fail ends in a plain reason
that hands the check to a person; the run always carries on.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from . import site

FUNCTION_URL = "https://production-sfo.browserless.io/function"
SESSION_MS = 45_000  # Browserless stops the session after this; 1 unit = 30 s, so a session is 1–2 units
RUN_CAP = 12  # browser sessions per run
MAX_STEPS = 8
VIEWPORTS = {
    "phone": {"width": 390, "height": 844, "isMobile": True, "hasTouch": True, "deviceScaleFactor": 1},
    "laptop": {"width": 1440, "height": 900, "deviceScaleFactor": 1},
}
# Never press these: they could pay, place an order, log in, or sign up / hand over details.
FORBIDDEN = (r"\b(pay|pay now|place order|complete order|confirm order|submit order|buy it now|buy now|"
             r"log ?in|sign ?in|sign ?up|register|create account|subscribe|unlock|spin)\b")
_JS = (Path(__file__).with_name("browser_fn.mjs")).read_text(encoding="utf-8")

HUMAN = {
    "payment": "Payment page, a person needs to check this",
    "login": "Login page, a person needs to check this",
    "captcha": "Bot check (captcha), a person needs to check this",
    "no_token": "The real browser isn't set up, a person needs to check this",
    "bad_token": "The real browser service didn't accept our key, a person needs to check this",
    "busy": "The real browser was busy, a person needs to check this",
    "units": "The real browser's units for this month are used up, a person needs to check this",
    "down": "The real browser service is unavailable right now, a person needs to check this",
    "slow": "The real browser took too long, a person needs to check this",
    "cap": "Browser limit for this run reached",
    "time": "Not enough time left for the real browser on this pair, a person needs to check this",
}


def token() -> str:
    """The Browserless token from the environment: BROWSERLESS_TOKEN, or any variable named *BROWSERLESS*."""
    value = os.environ.get("BROWSERLESS_TOKEN", "").strip()
    if value:
        return value
    for name, val in os.environ.items():
        if "BROWSERLESS" in name.upper() and val.strip():
            return val.strip()
    return ""


def configured() -> bool:
    return bool(token())


@dataclass
class Session:
    """What one browser session saw. `human_reason` set means: hand the browser checks to a person."""
    device: str
    status_code: int | None = None
    url: str = ""
    text: str = ""
    html: str = ""
    cart: dict | None = None
    shot: str | None = None  # base64 JPEG, kept in memory only for the vision judge, never stored
    notes: list[str] = field(default_factory=list)
    human_reason: str | None = None
    error: str | None = None

    def as_reply(self) -> site.SiteReply:
        """The rendered page as a SiteReply, so the plain-read checks can run on it."""
        return site.SiteReply(device=self.device, url=self.url, status_code=self.status_code,
                              text=self.text, html=self.html, json=self.cart,
                              summary=site.cart_summary(self.cart) if self.cart else None)

    def note(self) -> str:
        """Short text for what_site_said."""
        bits = ["Real browser"]
        if self.notes:
            bits.append(", ".join(self.notes[:6]))
        if self.cart:
            bits.append(site.cart_summary(self.cart))
        return " · ".join(bits)[:500]


# ---------------------------------------------------------------- steps

def clean_steps(raw, start_path: str | None = None) -> list[dict] | None:
    """Validate steps from the builder or the AI. Same-site paths only; raises ValueError in plain words."""
    if raw in (None, [], ""):
        return None
    if not isinstance(raw, list) or len(raw) > MAX_STEPS:
        raise ValueError(f"Steps must be a list of at most {MAX_STEPS} actions.")
    out = []
    for step in raw:
        if not isinstance(step, dict):
            raise ValueError("Each step must be one action, like open, click or wait.")
        if "goto" in step:
            path = step["goto"]
            if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or len(path) > 300:
                raise ValueError("A page to open must start with / (for example /products/solaris).")
            out.append({"goto": path})
        elif "click" in step:
            what = step["click"]
            if not isinstance(what, str) or not what.strip() or len(what) > 120:
                raise ValueError("Say what to click, for example text=Add to cart.")
            what = what.strip()
            if not what.startswith(("text=", "css=")):
                what = "text=" + what
            if re.search(FORBIDDEN, what.split("=", 1)[1], re.I):
                raise ValueError(f"We never click \"{what.split('=', 1)[1]}\": it could pay, order, log in or sign up.")
            item = {"click": what}
            if step.get("optional") is True:
                item["optional"] = True
            out.append(item)
        elif "wait" in step:
            try:
                secs = float(step["wait"])
            except (TypeError, ValueError):
                raise ValueError("Wait must be a number of seconds.")
            out.append({"wait": max(0.0, min(secs, 5.0))})
        elif "scroll" in step:
            out.append({"scroll": "bottom" if step["scroll"] == "bottom" else int(step["scroll"] or 0)})
        else:
            raise ValueError("Steps can open a page, click, wait or scroll.")
    return out


# ---------------------------------------------------------------- one session

def run(site_url: str, start_path: str, steps: list[dict] | None, device: str, want_shot: bool,
        want_cart: bool, want_html: bool = False, budget_s: float = SESSION_MS / 1000) -> Session:
    """One browser session on Browserless. Never raises; failures come back as `human_reason`."""
    s = Session(device=device)
    key = token()
    if not key:
        s.human_reason = HUMAN["no_token"]
        return s
    session_ms = int(min(SESSION_MS, budget_s * 1000))
    if session_ms < 15_000:
        s.human_reason = HUMAN["time"]
        return s
    context = {
        "base": site_url.rstrip("/"), "start": start_path or "/", "steps": steps or [],
        "ua": site.UA[device], "viewport": VIEWPORTS[device], "wantShot": want_shot, "wantCart": want_cart,
        "wantHtml": want_html, "forbidden": FORBIDDEN, "budgetMs": session_ms - 8_000,
    }
    for attempt in range(2):
        try:
            resp = requests.post(FUNCTION_URL, params={"token": key, "timeout": session_ms, "blockAds": "true"},
                                 json={"code": _JS, "context": context}, timeout=session_ms / 1000 + 8)
        except requests.Timeout:
            s.human_reason = HUMAN["slow"]
            return s
        except requests.RequestException:
            s.human_reason = HUMAN["down"]
            return s
        if resp.status_code == 429 and attempt == 0:
            time.sleep(5)  # busy (free plan: 2 browsers at once): wait once, then hand over
            continue
        break
    code = resp.status_code
    if code != 200:
        body = (resp.text or "").lower()
        if code in (401, 403) and "unit" not in body and "quota" not in body:
            s.human_reason = HUMAN["bad_token"]
        elif code == 429:
            s.human_reason = HUMAN["busy"]
        elif code == 402 or "unit" in body or "quota" in body or "limit" in body:
            s.human_reason = HUMAN["units"]
        elif code == 408:
            s.human_reason = HUMAN["slow"]
        else:
            s.human_reason = HUMAN["down"]
        return s
    try:
        data = resp.json()
    except ValueError:
        s.human_reason = HUMAN["down"]
        return s
    data = data.get("data", data) if isinstance(data, dict) else {}
    s.status_code = data.get("status")
    s.url = str(data.get("url") or "")
    s.text = str(data.get("text") or "")
    s.html = str(data.get("html") or "")
    s.cart = data.get("cart") if isinstance(data.get("cart"), dict) else None
    s.shot = data.get("shot") if isinstance(data.get("shot"), str) else None
    s.notes = [str(n) for n in data.get("notes") or []][:10]
    reason = data.get("human_reason")
    if reason:
        if str(reason).startswith("forbidden:"):
            s.human_reason = f"The next click (\"{str(reason)[10:]}\") could pay or place an order, a person needs to check this"
        else:
            s.human_reason = HUMAN.get(reason, HUMAN["down"])
    elif data.get("out_of_time"):
        s.human_reason = HUMAN["slow"]
    elif data.get("error"):
        s.error = str(data["error"])[:300]
    return s
