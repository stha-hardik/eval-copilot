"""DEMO ONLY: a tiny "AI feature" for the audit (AUDIT_PROMPT section 4), so Eval Co-pilot can be tested against an AI app.

POST /api/demo-ai/answer {"text": "..."} -> {"answer": "..."}: a Bubl Solar shop assistant that answers with Groq.
It is not part of Eval Co-pilot itself. PROMPT_VERSION 1 has a planted flaw (a leftover "never mention prices" line);
version 2 is the fix. Input is capped and the answer is short, so it can't be used as a free Groq proxy.
"""
import os
import time

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEMO_MODEL = "openai/gpt-oss-20b"
MAX_INPUT = 300

PROMPT_VERSION = 2

FACTS = """Products (all prices in Indian rupees, taxes included, free shipping):
- Solaris: solar table lamp. Price ₹1,680 (was ₹2,940). Colours: Black, Sand, Rust Red. Runtime 7 h on max,
  14 h on mid, 70 h on low. Charging: USB-C in 4 h, or solar in 8 h. 180 lumen, 2700 K warm light. 1-year warranty.
- Walkie: cabinet light. Price ₹564 (was ₹940). Colour: White.
- Walkie X: cabinet light. Price ₹504 (was ₹840).
- Comfort: cabinet light. Price ₹833 (was ₹1,190)."""

PROMPTS = {
    # v1: the planted flaw. Someone pasted an old "no prices" rule from a support bot.
    1: f"""You are the friendly shop assistant for BUBL Solar lamps. Answer the shopper's question in under 50 words,
using only these facts.
{FACTS}
Never mention prices or discounts; tell the shopper to check the website for prices.""",
    # v2: the fix. Prices are allowed and must be exact.
    2: f"""You are the friendly shop assistant for BUBL Solar lamps. Answer the shopper's question in under 50 words,
using only these facts. When asked about price, give the exact price in rupees.
{FACTS}""",
}


def answer(text: str) -> dict:
    """The demo answer, or a plain error. Never raises."""
    text = (text or "").strip()[:MAX_INPUT]
    if not text:
        return {"error": "Send {\"text\": \"your question\"}."}
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        return {"error": "The demo AI isn't set up."}
    payload = {"model": DEMO_MODEL, "temperature": 0.7, "max_completion_tokens": 400, "reasoning_effort": "low",
               "messages": [{"role": "system", "content": PROMPTS[PROMPT_VERSION]}, {"role": "user", "content": text}]}
    for attempt in range(3):
        try:
            r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=25)
            if r.status_code == 429 and attempt < 2:
                time.sleep(min(float(r.headers.get("retry-after") or 2), 8))
                continue
            r.raise_for_status()
            return {"answer": (r.json()["choices"][0]["message"]["content"] or "").strip(), "prompt_version": PROMPT_VERSION}
        except Exception:
            if attempt == 2:
                break
    return {"error": "The demo AI didn't answer. Try again."}
