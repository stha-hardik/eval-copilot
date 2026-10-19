"""M7 · the real browser, tested end to end through the API doors (api/index.py).

Nothing leaves this machine: Supabase is tests/fake_db.py, the plain page read is FakeSite (test_api.py), the
text AI is FakeGroq (test_api.py), and the two new outside helpers are faked HERE:
  * FakeBrowser replaces `browser.run`: scripted `browser.Session` objects, and it records every call
    (device, steps, flags, order, start and end times) so the tests can check the routing rules.
  * FakeVision replaces `groq.judge_screenshot`.
`site.run_code_check`, `site.excerpt`, `index._judge_device`, `groq.normalize_draft` and (in one test) the real
`groq.judge_screenshot` stay REAL.

The rules under test (from the owner's spec): code decides in a fixed order. Fetch for status_ok / text_has /
text_absent / min_results / count_equals / ai_judge; browser for browser_count / ai_vision (one session per pair +
device, one screenshot for all the vision checks); a thin or JavaScript-only page is retried once in the browser;
a person only for login / captcha / payment, vision unsure twice, Browserless trouble, or the 12-session run cap.
"""
from __future__ import annotations

import json
import os
import threading
import time
from types import SimpleNamespace

import pytest
import requests

from test_api import (  # noqa: F401  (fixtures `env` and `api` are used by name)
    BLOCKED_WHY, SITE_URL, TOK_A, ChunkOfNothing if False else None, api, chk, env, err, html, new_pair, new_project, ok,
) if False else None  # placeholder, replaced below
