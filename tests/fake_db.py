"""An in-memory stand-in for `supa.Db` (api/_lib/supa.py): same five methods, same errors.

It copies what Supabase would do for the tables in db/supabase_setup.sql:
  * defaults (uuid ids, increasing created_at, approved=false, method=GET, runs 0/0, ...),
  * NOT NULL / CHECK / UNIQUE / FOREIGN KEY rules (raised as SupaError exactly like `Db._req` maps them),
  * row level security: a token maps to a user; a user only sees rows that trace back to a project
    they own; writes to someone else's rows fail (insert -> SupaError(404, .., "42501"), update and
    delete -> nothing changes and [] comes back),
  * the per-table policies (results can't be updated or deleted; result_checks can only be updated
    while `passed` is null; runs/changes/diagnosis_points can't be deleted; ...),
  * the PostgREST query features index.py uses: eq / in / is / lt filters, order, limit, column lists
    and embedded resources (one-to-many -> list, many-to-one -> object).

Anything else raises NotImplementedError, so the fake never silently accepts a query it can't answer.

Simplifications versus real Supabase are listed in the final section of this file.
"""
from __future__ import annotations

import copy
import json
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_API_DIR = str(Path(__file__).resolve().parent.parent / "api")
if _API_DIR not in sys.path:  # index.py imports `_lib.supa`; the error class must be the very same one
    sys.path.insert(0, _API_DIR)

from _lib.supa import SupaError  # noqa: E402

USER_A = "00000000-0000-4000-8000-00000000000a"
USER_B = "00000000-0000-4000-8000-00000000000b"
DEFAULT_USERS = {"tok-A": USER_A, "tok-B": USER_B}


# ---------------------------------------------------------------- the schema (db/supabase_setup.sql)

def _new_id(ctx):
    return str(uuid.uuid4())


def _now(ctx):
    return ctx.store.now()


def _user(ctx):
    return ctx.user


ALL_OPS = {"select", "insert", "update", "delete"}

TABLES = {
    "projects": dict(
        cols=["id", "user_id", "name", "site_url", "created_at"],
        required=["name", "site_url"],
        defaults={"id": _new_id, "user_id": _user, "created_at": _now},
        ops=ALL_OPS,
    ),
    "golden_pairs": dict(
        cols=["id", "project_id", "position", "user_does", "good_result", "request_url", "method",
              "request_body", "source", "approved", "is_priority", "created_at"],
        required=["project_id", "position", "user_does", "good_result", "method", "source", "approved",
                  "is_priority"],
        defaults={"id": _new_id, "request_url": None, "method": "GET", "request_body": None,
                  "source": "builder", "approved": False, "is_priority": False, "created_at": _now},
        enums={"method": {"GET", "POST"}, "source": {"builder", "suggested"}},
        ops=ALL_OPS,
    ),
    "checks": dict(
        cols=["id", "golden_pair_id", "decided_by", "rule", "expected", "created_at"],
        required=["golden_pair_id", "decided_by", "rule"],
        defaults={"id": _new_id, "expected": None, "created_at": _now},
        enums={"decided_by": {"code", "ai", "human"},
               "rule": {"status_ok", "text_has", "text_absent", "count_equals", "min_results", "ai_judge",
                        "manual"}},
        ops=ALL_OPS,
    ),
    "runs": dict(
        cols=["id", "project_id", "run_number", "kind", "started_at", "passed", "total"],
        required=["project_id", "run_number", "kind", "passed", "total"],
        defaults={"id": _new_id, "kind": "full", "started_at": _now, "passed": 0, "total": 0},
        enums={"kind": {"full", "changed"}},
        unique=[("project_id", "run_number")],
        ops={"select", "insert", "update"},  # no delete: history is a row
    ),
    "results": dict(
        cols=["id", "run_id", "golden_pair_id", "device", "status_code", "what_site_said", "outcome",
              "created_at"],
        required=["run_id", "golden_pair_id", "device", "outcome"],
        defaults={"id": _new_id, "status_code": None, "what_site_said": None, "created_at": _now},
        enums={"device": {"phone", "laptop"}, "outcome": {"pass", "fail", "cant_test"}},
        unique=[("run_id", "golden_pair_id", "device")],
        ops={"select", "insert"},  # never update or delete: Run 1 can't be overwritten
    ),
    "result_checks": dict(
        cols=["id", "result_id", "check_id", "passed", "why"],
        required=["result_id", "check_id"],
        defaults={"id": _new_id, "passed": None, "why": None},
        unique=[("result_id", "check_id")],
        ops={"select", "insert", "update"},  # update only while passed is null (see _using_update)
    ),
    "changes": dict(
        cols=["id", "run_id", "golden_pair_id", "note", "created_at"],
        required=["run_id"],
        defaults={"id": _new_id, "golden_pair_id": None, "note": None, "created_at": _now},
        ops={"select", "insert"},
    ),
    "diagnosis_points": dict(
        cols=["id", "run_id", "result_id", "rank", "explanation"],
        required=["run_id", "result_id", "rank", "explanation"],
        defaults={"id": _new_id},
        ranges={"rank": (1, 3)},
        unique=[("run_id", "rank")],
        ops={"select", "insert"},
    ),
}

# (child table, column, parent table): used for integrity, cascade deletes, ownership and embedding
FKS = [
    ("golden_pairs", "project_id", "projects"),
    ("checks", "golden_pair_id", "golden_pairs"),
    ("runs", "project_id", "projects"),
    ("results", "run_id", "runs"),
    ("results", "golden_pair_id", "golden_pairs"),
    ("result_checks", "result_id", "results"),
    ("result_checks", "check_id", "checks"),
    ("changes", "run_id", "runs"),
    ("changes", "golden_pair_id", "golden_pairs"),
    ("diagnosis_points", "run_id", "runs"),
    ("diagnosis_points", "result_id", "results"),
]

# how a row proves it belongs to a project owner (RLS chain)
OWNER_PARENT = {
    "golden_pairs": ("project_id", "projects"),
    "checks": ("golden_pair_id", "golden_pairs"),
    "runs": ("project_id", "projects"),
    "results": ("run_id", "runs"),
    "result_checks": ("result_id", "results"),
    "changes": ("run_id", "runs"),
    "diagnosis_points": ("run_id", "runs"),
}

RESERVED = {"select", "order", "limit"}

# columns of type uuid: Postgres refuses anything else with 22P02 (PostgREST answers 400 -> Db maps it to 404)
UUID_COLS = {name: {"id"} | {col for child, col, _ in FKS if child == name} for name in TABLES}
UUID_COLS["projects"].add("user_id")


def _check_uuid(table: str, col: str, text):
    if col in UUID_COLS[table] and text is not None:
        try:
            uuid.UUID(str(text))
        except ValueError:
            raise _pg_error("22P02") from None


# ---------------------------------------------------------------- the shared store

class FakeStore(dict):
    """All tables of one fake database: {table: [row, ...]}. Shared by every FakeDb made for it."""

    def __init__(self, users: dict | None = None):
        super().__init__({name: [] for name in TABLES})
        self.users = dict(DEFAULT_USERS if users is None else users)  # token -> user id
        self.lock = threading.RLock()
        self._tick = 0
        self._base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # table -> callable(store, rows): runs once, just before the next insert into that table.
        # Lets a test simulate "another request got there first" (a race).
        self.before_insert: dict = {}

    def now(self) -> str:
        with self.lock:
            self._tick += 1
            return (self._base + timedelta(milliseconds=self._tick)).isoformat(timespec="microseconds")

    def user_of(self, token: str) -> str | None:
        return self.users.get(token)

    def user_info(self, token: str) -> dict | None:
        uid = self.user_of(token)
        return {"id": uid, "email": f"{uid[-1]}@example.com"} if uid else None

    def find(self, table: str, row_id) -> dict | None:
        return next((r for r in self[table] if r["id"] == row_id), None)

    def count(self, table: str, **equal) -> int:
        return sum(all(r.get(k) == v for k, v in equal.items()) for r in self[table])


def db_factory(store: FakeStore):
    """What to patch over `index.Db`: `lambda token: FakeDb(token, store)`."""
    return lambda token: FakeDb(token, store)


# ---------------------------------------------------------------- errors, like Db._req maps them

def _pg_error(code: str) -> SupaError:
    if code == "PGRST301":
        return SupaError(401, "Please log in again.", code)
    if code == "23505":
        return SupaError(409, "That was already saved.", code)
    if code in ("42501", "22P02"):  # mirrors supa.Db._req
        return SupaError(404, "We couldn't find that.", code)
    return SupaError(500, "The database said no. Please try again.", code)


# ---------------------------------------------------------------- filters

def _split_top(text: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts]


def _eq(value, text: str) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return text.lower() == str(value).lower()
    return str(value) == text


def _num(value):
    if isinstance(value, bool):
        raise NotImplementedError("fake_db: lt on a boolean")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _matches(table: str, row: dict, col: str, expr: str) -> bool:
    if col not in row:
        raise _pg_error("42703")
    op, _, arg = expr.partition(".")
    if op in ("eq", "lt"):
        _check_uuid(table, col, arg)
    elif op == "in":
        for item in arg.strip("()").split(","):
            if item.strip():
                _check_uuid(table, col, item.strip())
    value = row[col]
    if op == "eq":
        return _eq(value, arg)
    if op == "in":
        if not (arg.startswith("(") and arg.endswith(")")):
            raise NotImplementedError(f"fake_db: bad in filter {expr!r}")
        return any(_eq(value, item.strip()) for item in arg[1:-1].split(",") if item.strip())
    if op == "is":
        if arg == "null":
            return value is None
        if arg in ("true", "false"):
            return value is (arg == "true")
        raise NotImplementedError(f"fake_db: unsupported is filter {expr!r}")
    if op == "lt":
        if value is None:
            return False
        number = _num(value)
        return number < float(arg) if number is not None else str(value) < arg
    raise NotImplementedError(f"fake_db: unsupported filter {expr!r}")


def _filters(table: str, params: dict) -> list[tuple[str, str]]:
    """The column filters of a request. Postgres checks them when it parses the query, even if no row is
    there to compare with, so a bad column or a malformed uuid fails here and not only on a non-empty table."""
    out = [(k, v) for k, v in params.items() if k not in RESERVED]
    probe = {col: None for col in TABLES[table]["cols"]}
    for col, expr in out:
        _matches(table, probe, col, expr)
    return out


# ---------------------------------------------------------------- the Db stand-in

class _Ctx:
    def __init__(self, store: FakeStore, user: str):
        self.store, self.user = store, user


class FakeDb:
    """Same interface as supa.Db. One instance = one logged-in user (their token)."""

    def __init__(self, token: str, store: FakeStore):
        self.token = token
        self.store = store

    # ---- plumbing

    def _ctx(self, table: str) -> _Ctx:
        user = self.store.user_of(self.token)
        if not user:
            raise _pg_error("PGRST301")  # unknown / expired token, like Supabase's JWT error
        if table not in TABLES:
            raise _pg_error("PGRST205")
        return _Ctx(self.store, user)

    def _owner(self, table: str, row: dict | None):
        if row is None:
            return None
        if table == "projects":
            return row.get("user_id")
        col, parent = OWNER_PARENT[table]
        pid = row.get(col)
        return self._owner(parent, self.store.find(parent, pid)) if pid is not None else None

    def _visible(self, ctx: _Ctx, table: str) -> list[dict]:
        return [r for r in self.store[table] if self._owner(table, r) == ctx.user]

    @staticmethod
    def _using_update(table: str, row: dict) -> bool:
        # policy "human fills manual check": USING (passed is null AND ...)
        return row["passed"] is None if table == "result_checks" else True

    def _validate(self, ctx: _Ctx, table: str, row: dict, others: list[dict], ignore: dict | None):
        """NOT NULL, CHECK, UNIQUE, FOREIGN KEY for one finished row."""
        spec = TABLES[table]
        for col in spec["required"]:
            if row.get(col) is None:
                raise _pg_error("23502")
        for col, allowed in spec.get("enums", {}).items():
            if row.get(col) is not None and row[col] not in allowed:
                raise _pg_error("23514")
        for col, (low, high) in spec.get("ranges", {}).items():
            if not isinstance(row[col], int) or isinstance(row[col], bool) or not low <= row[col] <= high:
                raise _pg_error("23514")
        for child, col, parent in FKS:
            if child == table and row.get(col) is not None and self.store.find(parent, row[col]) is None:
                raise _pg_error("23503")
        for cols in spec.get("unique", []):
            key = tuple(row[c] for c in cols)
            for other in [*self.store[table], *others]:
                if other is ignore or other is row:
                    continue
                if tuple(other[c] for c in cols) == key:
                    raise _pg_error("23505")

    def _with_check(self, ctx: _Ctx, table: str, row: dict):
        """The RLS WITH CHECK of the insert / update policies. Fails with 42501."""
        if self._owner(table, row) != ctx.user:
            raise _pg_error("42501")
        if table == "results":  # the pair must belong to the same project as the run
            run, pair = self.store.find("runs", row["run_id"]), self.store.find("golden_pairs", row["golden_pair_id"])
            if not run or not pair or run["project_id"] != pair["project_id"]:
                raise _pg_error("42501")
        if table == "diagnosis_points":  # the result must belong to the run
            result = self.store.find("results", row["result_id"])
            if not result or result["run_id"] != row["run_id"]:
                raise _pg_error("42501")

    # ---- reading

    def select(self, table: str, **params: str) -> list[dict]:
        with self.store.lock:
            ctx = self._ctx(table)
            rows = self._visible(ctx, table)
            for col, expr in _filters(table, params):
                rows = [r for r in rows if _matches(table, r, col, expr)]
            if params.get("order"):
                for part in reversed(_split_top(params["order"])):
                    col, _, direction = part.partition(".")
                    if col not in TABLES[table]["cols"] or direction not in ("asc", "desc"):
                        raise NotImplementedError(f"fake_db: unsupported order {part!r}")
                    rows = sorted(rows, key=lambda r: (r[col] is None, r[col] if r[col] is not None else 0),
                                  reverse=direction == "desc")
            if params.get("limit") is not None:
                rows = rows[: int(params["limit"])]
            spec = params.get("select", "*")
            return [self._project(ctx, table, r, spec) for r in rows]

    def one(self, table: str, **params: str) -> dict | None:
        rows = self.select(table, limit="1", **params)
        return rows[0] if rows else None

    def _project(self, ctx: _Ctx, table: str, row: dict, spec: str) -> dict:
        out: dict = {}
        for item in _split_top(spec):
            if item == "*":
                out.update(copy.deepcopy(row))
            elif "(" in item:
                name, _, inner = item.partition("(")
                out[name] = self._embed(ctx, table, row, name, inner.rstrip(")"))
            elif item in row:
                out[item] = copy.deepcopy(row[item])
            else:
                raise _pg_error("42703")
        return out

    def _embed(self, ctx: _Ctx, table: str, row: dict, name: str, inner: str):
        for child, col, parent in FKS:  # one-to-many: rows of `name` pointing at this row
            if child == name and parent == table:
                kids = [k for k in self._visible(ctx, name) if k[col] == row["id"]]
                return [self._project(ctx, name, k, inner) for k in kids]
        for child, col, parent in FKS:  # many-to-one: the row this one points at
            if child == table and parent == name:
                target = self.store.find(name, row[col]) if row[col] is not None else None
                if target is None or self._owner(name, target) != ctx.user:
                    return None
                return self._project(ctx, name, target, inner)
        raise _pg_error("PGRST200")

    # ---- writing

    def insert(self, table: str, rows: dict | list[dict]) -> list[dict]:
        with self.store.lock:
            hook = self.store.before_insert.pop(table, None)
            if hook:
                hook(self.store, rows)
            ctx = self._ctx(table)
            spec = TABLES[table]
            rows = json.loads(json.dumps(rows))  # what the wire would do: JSON only
            batch = [rows] if isinstance(rows, dict) else rows
            staged: list[dict] = []
            for raw in batch:
                for col in raw:
                    if col not in spec["cols"]:
                        raise _pg_error("PGRST204")
                    _check_uuid(table, col, raw[col])
                if "insert" not in spec["ops"]:
                    raise _pg_error("42501")
                full = {}
                for col in spec["cols"]:
                    if col in raw:
                        full[col] = raw[col]
                    else:
                        default = spec["defaults"].get(col)
                        full[col] = default(ctx) if callable(default) else default
                if table == "projects" and full["user_id"] != ctx.user:
                    raise _pg_error("42501")
                for col in spec["required"]:  # NOT NULL is checked before RLS, like Postgres does
                    if full.get(col) is None:
                        raise _pg_error("23502")
                self._with_check(ctx, table, full)
                self._validate(ctx, table, full, staged, None)
                staged.append(full)
            self.store[table].extend(staged)  # one statement: all rows or none
            return copy.deepcopy(staged)

    def update(self, table: str, values: dict, **filters: str) -> list[dict]:
        with self.store.lock:
            ctx = self._ctx(table)
            spec = TABLES[table]
            values = json.loads(json.dumps(values))
            for col in values:
                if col not in spec["cols"]:
                    raise _pg_error("PGRST204")
                _check_uuid(table, col, values[col])
            if "update" not in spec["ops"]:
                return []  # no policy: no row is ever updatable
            targets = self._visible(ctx, table)
            for col, expr in _filters(table, filters):
                targets = [r for r in targets if _matches(table, r, col, expr)]
            targets = [r for r in targets if self._using_update(table, r)]
            new_rows = []
            for old in targets:
                new = {**old, **values}
                self._with_check(ctx, table, new)
                self._validate(ctx, table, new, [], old)
                new_rows.append((old, new))
            for old, new in new_rows:
                old.update(new)
            return copy.deepcopy([new for _, new in new_rows])

    def delete(self, table: str, **filters: str) -> list[dict]:
        with self.store.lock:
            ctx = self._ctx(table)
            if "delete" not in TABLES[table]["ops"]:
                return []
            targets = self._visible(ctx, table)
            for col, expr in _filters(table, filters):
                targets = [r for r in targets if _matches(table, r, col, expr)]
            gone = copy.deepcopy(targets)
            for row in targets:
                self._remove(table, row)
            return gone

    def _remove(self, table: str, row: dict):
        """Delete a row and, like ON DELETE CASCADE, everything pointing at it (RLS does not apply)."""
        for child, col, parent in FKS:
            if parent == table:
                for kid in [k for k in self.store[child] if k[col] == row["id"]]:
                    self._remove(child, kid)
        self.store[table][:] = [r for r in self.store[table] if r is not row]


# ---------------------------------------------------------------- what this fake simplifies
#  * Timestamps: every row gets its own, strictly increasing created_at. Real Postgres gives all rows of
#    one INSERT statement the same now(), so ordering by created_at inside a batch is a tie there.
#  * Rows come back in insertion order unless `order` is given (Postgres promises nothing).
#  * Column types are barely enforced: only uuid columns are (a bad uuid gives 22P02 like Postgres) and
#    values must survive a JSON round-trip. No int/boolean/timestamptz parsing or casting.
#  * Each call is its own transaction; there is no isolation level, no deadlocks, no sequences.
#    A race is only simulated through `FakeStore.before_insert`.
#  * `Prefer: return=representation` is always on; PostgREST's 406/416 and pagination caps don't exist.
#  * RLS is modelled by ownership chains and the policies in the SQL file only. The `anon` role and
#    expired JWT timing are reduced to "unknown token -> 401".
#  * Foreign keys are checked on insert/update and cascade on delete; RESTRICT / SET NULL do not exist
#    in this schema.
