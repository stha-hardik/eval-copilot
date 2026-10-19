"""Supabase over plain HTTP: login (Auth API) and table access (REST API) as the logged-in user.

We only ever use the public anon key plus the user's own access token, so Supabase's Row Level
Security rules apply to every read and write. There is no service-role key anywhere.
"""
import os
from typing import Any

import requests

TIMEOUT = 15


class SupaError(Exception):
    """A Supabase call failed. `status` is what we answer the browser; `code` is Postgres' error code."""

    def __init__(self, status: int, message: str, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


def _base() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise SupaError(500, "The server is missing its database settings.")
    return url, key


# ---------------------------------------------------------------- auth

def _session(data: dict) -> dict:
    user = data.get("user") or {}
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": data.get("expires_at"),
        "user": {"id": user.get("id"), "email": user.get("email")},
    }


def _auth_post(path: str, body: dict) -> requests.Response:
    url, key = _base()
    try:
        return requests.post(f"{url}/auth/v1/{path}", json=body, timeout=TIMEOUT,
                             headers={"apikey": key, "Content-Type": "application/json"})
    except requests.RequestException:
        raise SupaError(503, "We couldn't reach the login service. Please try again.")


def _auth_message(r: requests.Response) -> str:
    try:
        d = r.json()
    except ValueError:
        return ""
    return str(d.get("msg") or d.get("error_description") or d.get("message") or d.get("error") or "")


def signup(email: str, password: str) -> dict:
    r = _auth_post("signup", {"email": email, "password": password})
    if r.status_code >= 400:
        msg = _auth_message(r)
        if "registered" in msg.lower() or "exists" in msg.lower():
            raise SupaError(400, "That email already has an account. Log in instead.")
        if "password" in msg.lower():
            raise SupaError(400, "Please pick a stronger password (at least 8 characters).")
        if r.status_code == 429:
            raise SupaError(429, "Too many sign-ups just now. Please wait a minute and try again.")
        raise SupaError(400, "We couldn't create that account. Check the email and password.")
    data = r.json()
    if not data.get("access_token"):
        # Supabase sends a confirmation email first when "Confirm email" is on.
        raise SupaError(409, "Check your email to confirm your account, then log in.")
    return _session(data)


def login(email: str, password: str) -> dict:
    r = _auth_post("token?grant_type=password", {"email": email, "password": password})
    if r.status_code >= 400:
        if "confirm" in _auth_message(r).lower():
            raise SupaError(401, "Please confirm your email first, then log in.")
        raise SupaError(401, "That email and password don't match.")
    return _session(r.json())


def refresh(refresh_token: str) -> dict:
    r = _auth_post("token?grant_type=refresh_token", {"refresh_token": refresh_token})
    if r.status_code >= 400:
        raise SupaError(401, "Please log in again.")
    return _session(r.json())


def get_user(token: str) -> dict:
    """Check an access token with Supabase and return {id, email}. Raises 401 if not valid."""
    url, key = _base()
    try:
        r = requests.get(f"{url}/auth/v1/user", timeout=TIMEOUT,
                         headers={"apikey": key, "Authorization": f"Bearer {token}"})
    except requests.RequestException:
        raise SupaError(503, "We couldn't reach the login service. Please try again.")
    if r.status_code != 200:
        raise SupaError(401, "Please log in again.")
    d = r.json()
    return {"id": d.get("id"), "email": d.get("email")}


# ---------------------------------------------------------------- tables

class Db:
    """Table access as one user. Every call carries their token, so RLS decides what they can touch."""

    def __init__(self, token: str):
        self.url, key = _base()
        self.headers = {"apikey": key, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _req(self, method: str, table: str, params: dict | None = None, body: Any = None,
             prefer: str | None = None) -> Any:
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        try:
            r = requests.request(method, f"{self.url}/rest/v1/{table}", params=params, json=body,
                                 headers=headers, timeout=TIMEOUT)
        except requests.RequestException:
            raise SupaError(503, "We couldn't reach the database. Please try again.")
        if r.status_code >= 400:
            try:
                err = r.json()
            except ValueError:
                err = {}
            code = err.get("code")
            if r.status_code == 401 or code in ("PGRST301", "PGRST303"):
                raise SupaError(401, "Please log in again.", code)
            if code == "23505":
                raise SupaError(409, "That was already saved.", code)
            if code == "42501":
                raise SupaError(404, "We couldn't find that.", code)
            raise SupaError(500, "The database said no. Please try again.", code)
        if r.status_code == 204 or not r.content:
            return []
        return r.json()

    def select(self, table: str, **params: str) -> list[dict]:
        return self._req("GET", table, params=params)

    def one(self, table: str, **params: str) -> dict | None:
        rows = self.select(table, limit="1", **params)
        return rows[0] if rows else None

    def insert(self, table: str, rows: dict | list[dict]) -> list[dict]:
        return self._req("POST", table, body=rows, prefer="return=representation")

    def update(self, table: str, values: dict, **filters: str) -> list[dict]:
        return self._req("PATCH", table, params=filters, body=values, prefer="return=representation")

    def delete(self, table: str, **filters: str) -> list[dict]:
        return self._req("DELETE", table, params=filters, prefer="return=representation")


def in_list(ids: list) -> str:
    """PostgREST `in` filter value for a list of ids."""
    return "in.(" + ",".join(str(i) for i in ids) + ")"
