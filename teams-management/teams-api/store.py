"""SQLite persistence for teams, ownership and per-namespace access grants.

This module is the **system of record for authorization**. Keycloak remains the
identity provider (who exists, who can log in), but who owns which team and who
holds which role in which namespace lives here. Reading authority from a live
database rather than from the JWT means a change takes effect on the caller's
very next request — no token refresh, which is what the `groups`-claim model
required.

Identity is keyed on the Keycloak `sub` (`user_id`), never the username:
usernames are mutable in Keycloak and would silently re-point a grant. The
username is stored alongside purely for display and is refreshed opportunistically.

Concurrency: the deployment is `replicas: 1` with `strategy: Recreate` on a
ReadWriteOnce PVC, so exactly one writer ever touches the file. A module-level
connection (``check_same_thread=False``) guarded by a lock is therefore enough —
FastAPI runs sync routes in a threadpool, so the lock is what keeps those safe.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

log = logging.getLogger("teams-api.store")

DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_FILE = Path(DATA_DIR) / "teams.db"

# The two roles a user can hold *in a namespace*. Ownership of the team confers
# `maintainer` implicitly (see authz.namespace_role) and is not stored per-namespace.
ROLES = ("viewer", "maintainer")

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_namespaces (
    namespace   TEXT PRIMARY KEY,
    team_id     TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    is_default  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS team_owners (
    team_id     TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    username    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (team_id, user_id)
);

CREATE TABLE IF NOT EXISTS namespace_grants (
    namespace   TEXT NOT NULL REFERENCES team_namespaces(namespace) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    username    TEXT NOT NULL DEFAULT '',
    role        TEXT NOT NULL CHECK (role IN ('viewer', 'maintainer')),
    PRIMARY KEY (namespace, user_id)
);

CREATE TABLE IF NOT EXISTS audit (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    actor   TEXT NOT NULL DEFAULT '',
    action  TEXT NOT NULL,
    target  TEXT NOT NULL DEFAULT '',
    detail  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_ns_team   ON team_namespaces(team_id);
CREATE INDEX IF NOT EXISTS idx_owner_uid ON team_owners(user_id);
CREATE INDEX IF NOT EXISTS idx_grant_uid ON namespace_grants(user_id);
"""

_conn: Optional[sqlite3.Connection] = None
_lock = threading.RLock()


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    """Open (once) and initialise the database. Safe to call repeatedly."""
    global _conn
    with _lock:
        if _conn is not None:
            return _conn
        db_path = Path(path) if path else DB_FILE
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL keeps reads from blocking behind a write; harmless on a single writer.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
        _conn = conn
        log.info("SQLite store ready at %s", db_path)
        return _conn


def _db() -> sqlite3.Connection:
    return _conn if _conn is not None else connect()


def close() -> None:
    """Close the connection (tests; the process otherwise holds it for its lifetime)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def record(actor: str, action: str, target: str = "", detail: str = "") -> None:
    """Append an audit row. Never raises — losing an audit line must not fail a request."""
    try:
        with _lock:
            _db().execute(
                "INSERT INTO audit (ts, actor, action, target, detail) VALUES (?,?,?,?,?)",
                (datetime.now().isoformat(), actor or "", action, target, detail),
            )
            _db().commit()
    except Exception as e:  # noqa: BLE001
        log.error("audit write failed (%s %s): %s", action, target, e)


def audit_tail(limit: int = 100) -> List[dict]:
    rows = _db().execute(
        "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Teams
# --------------------------------------------------------------------------- #
def _team_row_to_dict(row: sqlite3.Row) -> dict:
    """Shape a team the way the rest of the API expects.

    `namespaces` as a plain list keeps workloads.py / compliance.py working
    unchanged — they consume `team["namespaces"]`.
    """
    return {
        "id": row["id"],
        "name": row["name"],
        "created_at": row["created_at"],
        "namespaces": namespaces_of(row["id"]),
    }


def list_teams() -> List[dict]:
    rows = _db().execute("SELECT * FROM teams ORDER BY name").fetchall()
    return [_team_row_to_dict(r) for r in rows]


def get_team(team_id: str) -> Optional[dict]:
    row = _db().execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    return _team_row_to_dict(row) if row else None


def team_name_exists(name: str) -> bool:
    row = _db().execute(
        "SELECT 1 FROM teams WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    return row is not None


def create_team(team_id: str, name: str, namespace: str, created_at: str = "") -> dict:
    with _lock:
        _db().execute(
            "INSERT INTO teams (id, name, created_at) VALUES (?,?,?)",
            (team_id, name, created_at or datetime.now().isoformat()),
        )
        _db().execute(
            "INSERT INTO team_namespaces (namespace, team_id, is_default) VALUES (?,?,1)",
            (namespace, team_id),
        )
        _db().commit()
    return get_team(team_id)  # type: ignore[return-value]


def delete_team(team_id: str) -> None:
    """Delete a team. Namespaces, owners and grants cascade (see FKs)."""
    with _lock:
        _db().execute("DELETE FROM teams WHERE id = ?", (team_id,))
        _db().commit()


# --------------------------------------------------------------------------- #
# Namespaces
# --------------------------------------------------------------------------- #
def namespaces_of(team_id: str) -> List[str]:
    rows = _db().execute(
        "SELECT namespace FROM team_namespaces WHERE team_id = ? "
        "ORDER BY is_default DESC, namespace",
        (team_id,),
    ).fetchall()
    return [r["namespace"] for r in rows]


def all_namespaces() -> Set[str]:
    rows = _db().execute("SELECT namespace FROM team_namespaces").fetchall()
    return {r["namespace"] for r in rows}


def team_for_namespace(namespace: str) -> Optional[dict]:
    row = _db().execute(
        "SELECT team_id FROM team_namespaces WHERE namespace = ?", (namespace,)
    ).fetchone()
    return get_team(row["team_id"]) if row else None


def namespace_exists(namespace: str) -> bool:
    row = _db().execute(
        "SELECT 1 FROM team_namespaces WHERE namespace = ?", (namespace,)
    ).fetchone()
    return row is not None


def is_default_namespace(namespace: str) -> bool:
    row = _db().execute(
        "SELECT is_default FROM team_namespaces WHERE namespace = ?", (namespace,)
    ).fetchone()
    return bool(row and row["is_default"])


def default_namespace_of(team_id: str) -> Optional[str]:
    """The team's default namespace, or None once it's been deleted (the
    default namespace is no longer protected from deletion — see main.py's
    delete_namespace)."""
    row = _db().execute(
        "SELECT namespace FROM team_namespaces WHERE team_id = ? AND is_default = 1",
        (team_id,),
    ).fetchone()
    return row["namespace"] if row else None


def add_namespace(team_id: str, namespace: str, is_default: bool = False) -> None:
    with _lock:
        _db().execute(
            "INSERT INTO team_namespaces (namespace, team_id, is_default) VALUES (?,?,?)",
            (namespace, team_id, 1 if is_default else 0),
        )
        _db().commit()


def remove_namespace(namespace: str) -> None:
    """Remove a namespace. Its grants cascade away."""
    with _lock:
        _db().execute("DELETE FROM team_namespaces WHERE namespace = ?", (namespace,))
        _db().commit()


# --------------------------------------------------------------------------- #
# Ownership
# --------------------------------------------------------------------------- #
def owners_of(team_id: str) -> List[dict]:
    rows = _db().execute(
        "SELECT user_id, username FROM team_owners WHERE team_id = ? ORDER BY username",
        (team_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def owned_team_ids(user_id: str) -> Set[str]:
    if not user_id:
        return set()
    rows = _db().execute(
        "SELECT team_id FROM team_owners WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {r["team_id"] for r in rows}


def is_owner(user_id: str, team_id: str) -> bool:
    if not user_id:
        return False
    row = _db().execute(
        "SELECT 1 FROM team_owners WHERE team_id = ? AND user_id = ?",
        (team_id, user_id),
    ).fetchone()
    return row is not None


def add_owner(team_id: str, user_id: str, username: str = "") -> None:
    with _lock:
        _db().execute(
            "INSERT INTO team_owners (team_id, user_id, username) VALUES (?,?,?) "
            "ON CONFLICT(team_id, user_id) DO UPDATE SET username = excluded.username",
            (team_id, user_id, username),
        )
        _db().commit()


def remove_owner(team_id: str, user_id: str) -> None:
    with _lock:
        _db().execute(
            "DELETE FROM team_owners WHERE team_id = ? AND user_id = ?",
            (team_id, user_id),
        )
        _db().commit()


# --------------------------------------------------------------------------- #
# Per-namespace grants
# --------------------------------------------------------------------------- #
def set_grant(namespace: str, user_id: str, username: str, role: str) -> None:
    """Grant or change a user's role in a namespace (upsert — one path for both)."""
    if role not in ROLES:
        raise ValueError(f"invalid role: {role}")
    with _lock:
        _db().execute(
            "INSERT INTO namespace_grants (namespace, user_id, username, role) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(namespace, user_id) DO UPDATE SET "
            "role = excluded.role, username = excluded.username",
            (namespace, user_id, username, role),
        )
        _db().commit()


def remove_grant(namespace: str, user_id: str) -> None:
    with _lock:
        _db().execute(
            "DELETE FROM namespace_grants WHERE namespace = ? AND user_id = ?",
            (namespace, user_id),
        )
        _db().commit()


def grants_for_namespace(namespace: str) -> List[dict]:
    rows = _db().execute(
        "SELECT user_id, username, role FROM namespace_grants WHERE namespace = ? "
        "ORDER BY username",
        (namespace,),
    ).fetchall()
    return [dict(r) for r in rows]


def grants_for_user(user_id: str) -> Dict[str, str]:
    """namespace -> role for every explicit grant this user holds."""
    if not user_id:
        return {}
    rows = _db().execute(
        "SELECT namespace, role FROM namespace_grants WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {r["namespace"]: r["role"] for r in rows}


def grant_role(namespace: str, user_id: str) -> Optional[str]:
    if not user_id:
        return None
    row = _db().execute(
        "SELECT role FROM namespace_grants WHERE namespace = ? AND user_id = ?",
        (namespace, user_id),
    ).fetchone()
    return row["role"] if row else None


def refresh_usernames(users_by_id: Dict[str, str]) -> None:
    """Re-sync the denormalised usernames from Keycloak (ids are authoritative)."""
    if not users_by_id:
        return
    with _lock:
        for uid, uname in users_by_id.items():
            _db().execute(
                "UPDATE team_owners SET username = ? WHERE user_id = ? AND username != ?",
                (uname, uid, uname),
            )
            _db().execute(
                "UPDATE namespace_grants SET username = ? WHERE user_id = ? AND username != ?",
                (uname, uid, uname),
            )
        _db().commit()


# --------------------------------------------------------------------------- #
# One-time migration from the legacy JSON store + Keycloak groups
# --------------------------------------------------------------------------- #
def migrate_from_legacy_json(
    json_path: Path,
    members_of,
    users_by_name: Dict[str, dict],
    leaders: Set[str],
    default_namespace_of,
) -> dict:
    """Seed the database from `teams.json` + current Keycloak group membership.

    Runs only when the database has no teams, so re-running is a no-op. This is
    what preserves everyone's existing access across the cutover: each namespace's
    Keycloak group members become grants, and members holding the legacy
    `team-leader` realm role become **owners** of the team.

    `members_of(ns) -> [username]`, `users_by_name` maps username -> Keycloak user
    (needs `id`), `leaders` is the set of usernames holding `team-leader`, and
    `default_namespace_of(team_name) -> str` identifies the non-deletable namespace.

    Returns a summary dict for logging. The JSON file is left untouched as a backup.
    """
    summary = {"teams": 0, "namespaces": 0, "owners": 0, "grants": 0, "skipped": []}

    if _db().execute("SELECT 1 FROM teams LIMIT 1").fetchone():
        return {**summary, "status": "already-migrated"}
    if not Path(json_path).exists():
        return {**summary, "status": "no-legacy-data"}

    try:
        with Path(json_path).open() as f:
            legacy = json.load(f)
    except Exception as e:  # noqa: BLE001 - a bad backup file must not block startup
        log.error("Could not read legacy store %s: %s", json_path, e)
        return {**summary, "status": "unreadable"}

    for team in legacy:
        team_id, name = team.get("id"), team.get("name")
        if not team_id or not name:
            continue
        nss = team.get("namespaces") or [default_namespace_of(name)]
        default_ns = default_namespace_of(name)

        with _lock:
            _db().execute(
                "INSERT OR IGNORE INTO teams (id, name, created_at) VALUES (?,?,?)",
                (team_id, name, team.get("created_at") or datetime.now().isoformat()),
            )
            for ns in nss:
                _db().execute(
                    "INSERT OR IGNORE INTO team_namespaces (namespace, team_id, is_default) "
                    "VALUES (?,?,?)",
                    (ns, team_id, 1 if ns == default_ns else 0),
                )
            _db().commit()
        summary["teams"] += 1
        summary["namespaces"] += len(nss)

        # Derive owners + grants from the Keycloak groups this replaces.
        for ns in nss:
            try:
                members = members_of(ns)
            except Exception as e:  # noqa: BLE001 - partial migration beats none
                log.error("Could not read members of %s: %s", ns, e)
                summary["skipped"].append(ns)
                continue
            for uname in members:
                user = users_by_name.get(uname)
                if not user or not user.get("id"):
                    summary["skipped"].append(f"{ns}:{uname}")
                    continue
                uid = user["id"]
                if uname in leaders:
                    add_owner(team_id, uid, uname)
                    summary["owners"] += 1
                else:
                    set_grant(ns, uid, uname, "viewer")
                    summary["grants"] += 1

    record("system", "migrate", "legacy-json", json.dumps(summary, default=str))
    return {**summary, "status": "migrated"}
