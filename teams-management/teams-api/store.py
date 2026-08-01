"""SQLite persistence for projects, ownership and per-namespace access grants.

This module is the **system of record for authorization**. Keycloak remains the
identity provider (who exists, who can log in), but who owns which project and who
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

# The two roles a user can hold *in a namespace*. Ownership of the project confers
# `maintainer` implicitly (see authz.namespace_role) and is not stored per-namespace.
ROLES = ("viewer", "maintainer")

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_namespaces (
    namespace   TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    is_default  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS project_owners (
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    username    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (project_id, user_id)
);

CREATE TABLE IF NOT EXISTS namespace_grants (
    namespace   TEXT NOT NULL REFERENCES project_namespaces(namespace) ON DELETE CASCADE,
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

-- Source repos a project's Argo CD AppProject should allow (self-service:
-- an admin or that project's manager/owner adds these; teams-operator
-- reconciles them into the AppProject's sourceRepos - see
-- ensure_argocd_appproject in teams_operator.py). Deliberately its own table
-- rather than a column on `projects`: a project can have any number of repos.
-- `installation_id` is the GitHub App installation this repo was connected
-- through (see docs/self-service-repos-github-app.md); '' means "not connected"
-- (public repo, or connection pending). It is an identifier, NOT a secret - the
-- only secret (the App private key) lives in OpenBao, never here.
-- `connection_id` is which registered GitHub App connection (github_app_connections)
-- minted that installation; '' means the legacy single platform App (or a public
-- repo). teams-operator uses it to pick the right App key + id per repo.
CREATE TABLE IF NOT EXISTS project_source_repos (
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    repo_url        TEXT NOT NULL,
    installation_id TEXT NOT NULL DEFAULT '',
    connection_id   TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (project_id, repo_url)
);

-- Registered GitHub App "connections" a project may connect repos through
-- (see docs/self-service-repos-github-app.md). Per-project (a connection belongs
-- to the project that registered it). Created via GitHub's App Manifest flow: a
-- row is inserted 'pending' when the manifest-callback fires, then teams-operator
-- exchanges the one-time code for the App's id/slug/private-key, writes the key
-- to OpenBao (kv/platform/github-apps/<id>) and reports the non-secret metadata
-- back, flipping the row to 'ready'. `app_id`/`slug` are identifiers, NOT secrets.
CREATE TABLE IF NOT EXISTS github_app_connections (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL DEFAULT '',
    slug        TEXT NOT NULL DEFAULT '',
    app_id      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready')),
    created_by  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

-- Pending GitHub App Manifest exchanges awaiting teams-operator (which performs
-- the code->key conversion so teams-api never holds the App key). One row per
-- connection being registered; `code` is GitHub's single-use, ~1h manifest
-- conversion code. Deleted once the operator resolves it.
CREATE TABLE IF NOT EXISTS github_app_registrations (
    connection_id TEXT PRIMARY KEY REFERENCES github_app_connections(id) ON DELETE CASCADE,
    project_id    TEXT NOT NULL,
    code          TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

-- Admin-curated global whitelist of repos available to EVERY project (see
-- docs/self-service-repos-github-app.md). teams-api unions these with each
-- project's own repos in /internal/teams, so the operator reconciles the
-- effective set into every AppProject's sourceRepos.
CREATE TABLE IF NOT EXISTS global_source_repos (
    repo_url    TEXT PRIMARY KEY
);

-- Pending GitHub App connections awaiting resolution (see
-- docs/self-service-repos-github-app.md). When a user finishes the "pick repos
-- on GitHub" flow, the callback records (target, installation_id) here — teams-api
-- never holds the App key, so it cannot enumerate the repos itself. teams-operator
-- (which does hold the key) polls these, resolves each installation to its repo
-- list, and reports them back (/internal/github-connections/resolve), which adds
-- the repos and deletes the row. `target` is a project id or the literal 'global'.
CREATE TABLE IF NOT EXISTS github_connections (
    target          TEXT NOT NULL,
    installation_id TEXT NOT NULL,
    connection_id   TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    PRIMARY KEY (target, installation_id)
);

CREATE INDEX IF NOT EXISTS idx_ns_project ON project_namespaces(project_id);
CREATE INDEX IF NOT EXISTS idx_owner_uid  ON project_owners(user_id);
CREATE INDEX IF NOT EXISTS idx_grant_uid  ON namespace_grants(user_id);
CREATE INDEX IF NOT EXISTS idx_repo_project ON project_source_repos(project_id);
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
        _migrate_stale_namespace_grants_fk(conn)
        _migrate_add_repo_installation_column(conn)
        _migrate_add_connection_id_columns(conn)
        _conn = conn
        log.info("SQLite store ready at %s", db_path)
        return _conn


def _migrate_stale_namespace_grants_fk(conn: sqlite3.Connection) -> None:
    """Repair a DB created before the team->project rename.

    `namespace_grants`'s FK is baked in at CREATE TABLE time, and its own table
    name never changed across the rename, so `CREATE TABLE IF NOT EXISTS`
    never rewrote it: a DB that predates the rename still enforces
    `REFERENCES team_namespaces(namespace)` even though every namespace now
    lives in `project_namespaces`. Every grant on a namespace created after
    the rename then fails FOREIGN KEY constraint failed (add_owner/
    project_owners doesn't share this problem - that table name never
    collided with a pre-rename one, so it was created fresh with the right
    FK). Rebuilds the table against `project_namespaces`, keeping any row
    whose namespace still has a home there and dropping the rest (they'd be
    unreachable orphans anyway - their project is long gone).
    """
    fk = conn.execute("PRAGMA foreign_key_list(namespace_grants)").fetchall()
    if not any(row["table"] == "team_namespaces" for row in fk):
        return
    log.warning("Migrating namespace_grants off legacy team_namespaces FK reference")
    conn.execute("ALTER TABLE namespace_grants RENAME TO namespace_grants_legacy")
    conn.execute(
        """
        CREATE TABLE namespace_grants (
            namespace   TEXT NOT NULL REFERENCES project_namespaces(namespace) ON DELETE CASCADE,
            user_id     TEXT NOT NULL,
            username    TEXT NOT NULL DEFAULT '',
            role        TEXT NOT NULL CHECK (role IN ('viewer', 'maintainer')),
            PRIMARY KEY (namespace, user_id)
        )
        """
    )
    conn.execute(
        "INSERT INTO namespace_grants (namespace, user_id, username, role) "
        "SELECT namespace, user_id, username, role FROM namespace_grants_legacy "
        "WHERE namespace IN (SELECT namespace FROM project_namespaces)"
    )
    conn.execute("DROP TABLE namespace_grants_legacy")
    # The pre-rename tables (teams/team_namespaces/team_owners) are now fully
    # orphaned - no code references them and namespace_grants no longer does
    # either. Drop them rather than leave dead, confusing tables behind.
    for legacy_table in ("team_namespaces", "team_owners", "teams"):
        conn.execute(f"DROP TABLE IF EXISTS {legacy_table}")
    conn.commit()


def _migrate_add_repo_installation_column(conn: sqlite3.Connection) -> None:
    """Add project_source_repos.installation_id to a DB created before the
    GitHub App feature. `CREATE TABLE IF NOT EXISTS` never adds a column to an
    existing table, so a pre-feature DB is missing it; every repo insert/read
    that references the column would then fail. Idempotent: checks PRAGMA first."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(project_source_repos)")}
    if "installation_id" in cols:
        return
    log.warning("Migrating project_source_repos: adding installation_id column")
    conn.execute(
        "ALTER TABLE project_source_repos ADD COLUMN installation_id TEXT NOT NULL DEFAULT ''"
    )
    conn.commit()


def _migrate_add_connection_id_columns(conn: sqlite3.Connection) -> None:
    """Add the `connection_id` columns introduced with multi-connection GitHub
    App support (see docs/self-service-repos-github-app.md) to DBs created before
    it. `CREATE TABLE IF NOT EXISTS` never adds a column to an existing table.
    Idempotent: checks PRAGMA per table first. The github_app_connections /
    github_app_registrations tables themselves are handled by CREATE IF NOT
    EXISTS in the schema, so they need no migration here."""
    repo_cols = {r["name"] for r in conn.execute("PRAGMA table_info(project_source_repos)")}
    if "connection_id" not in repo_cols:
        log.warning("Migrating project_source_repos: adding connection_id column")
        conn.execute(
            "ALTER TABLE project_source_repos ADD COLUMN connection_id TEXT NOT NULL DEFAULT ''"
        )
    conn_cols = {r["name"] for r in conn.execute("PRAGMA table_info(github_connections)")}
    if "connection_id" not in conn_cols:
        log.warning("Migrating github_connections: adding connection_id column")
        conn.execute(
            "ALTER TABLE github_connections ADD COLUMN connection_id TEXT NOT NULL DEFAULT ''"
        )
    conn.commit()


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
# Projects
# --------------------------------------------------------------------------- #
def _project_row_to_dict(row: sqlite3.Row) -> dict:
    """Shape a project the way the rest of the API expects.

    `namespaces` as a plain list keeps workloads.py / compliance.py working
    unchanged — they consume `project["namespaces"]`.
    """
    return {
        "id": row["id"],
        "name": row["name"],
        "created_at": row["created_at"],
        "namespaces": namespaces_of(row["id"]),
    }


def list_projects() -> List[dict]:
    rows = _db().execute("SELECT * FROM projects ORDER BY name").fetchall()
    return [_project_row_to_dict(r) for r in rows]


def get_project(project_id: str) -> Optional[dict]:
    row = _db().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _project_row_to_dict(row) if row else None


def project_name_exists(name: str) -> bool:
    row = _db().execute(
        "SELECT 1 FROM projects WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    return row is not None


def create_project(
    project_id: str, name: str, namespace: str, created_at: str = "",
    source_repos: Optional[List[str]] = None,
) -> dict:
    """Create a project + its default namespace, and (optionally) its initial
    source repos — all in one transaction, so a repo insert failing can't leave
    a half-created project behind (source repos are mandatory at creation now;
    see main.py create_project / docs/self-service-repos-github-app.md)."""
    with _lock:
        _db().execute(
            "INSERT INTO projects (id, name, created_at) VALUES (?,?,?)",
            (project_id, name, created_at or datetime.now().isoformat()),
        )
        _db().execute(
            "INSERT INTO project_namespaces (namespace, project_id, is_default) VALUES (?,?,1)",
            (namespace, project_id),
        )
        for repo_url in source_repos or []:
            _db().execute(
                "INSERT OR IGNORE INTO project_source_repos (project_id, repo_url) VALUES (?,?)",
                (project_id, repo_url),
            )
        _db().commit()
    return get_project(project_id)  # type: ignore[return-value]


def delete_project(project_id: str) -> None:
    """Delete a project. Namespaces, owners and grants cascade (see FKs)."""
    with _lock:
        _db().execute("DELETE FROM projects WHERE id = ?", (project_id,))
        _db().commit()


# --------------------------------------------------------------------------- #
# Namespaces
# --------------------------------------------------------------------------- #
def namespaces_of(project_id: str) -> List[str]:
    rows = _db().execute(
        "SELECT namespace FROM project_namespaces WHERE project_id = ? "
        "ORDER BY is_default DESC, namespace",
        (project_id,),
    ).fetchall()
    return [r["namespace"] for r in rows]


def all_namespaces() -> Set[str]:
    rows = _db().execute("SELECT namespace FROM project_namespaces").fetchall()
    return {r["namespace"] for r in rows}


def project_for_namespace(namespace: str) -> Optional[dict]:
    row = _db().execute(
        "SELECT project_id FROM project_namespaces WHERE namespace = ?", (namespace,)
    ).fetchone()
    return get_project(row["project_id"]) if row else None


def namespace_exists(namespace: str) -> bool:
    row = _db().execute(
        "SELECT 1 FROM project_namespaces WHERE namespace = ?", (namespace,)
    ).fetchone()
    return row is not None


def is_default_namespace(namespace: str) -> bool:
    row = _db().execute(
        "SELECT is_default FROM project_namespaces WHERE namespace = ?", (namespace,)
    ).fetchone()
    return bool(row and row["is_default"])


def default_namespace_of(project_id: str) -> Optional[str]:
    """The project's default namespace, or None once it's been deleted (the
    default namespace is no longer protected from deletion — see main.py's
    delete_namespace)."""
    row = _db().execute(
        "SELECT namespace FROM project_namespaces WHERE project_id = ? AND is_default = 1",
        (project_id,),
    ).fetchone()
    return row["namespace"] if row else None


def add_namespace(project_id: str, namespace: str, is_default: bool = False) -> None:
    with _lock:
        _db().execute(
            "INSERT INTO project_namespaces (namespace, project_id, is_default) VALUES (?,?,?)",
            (namespace, project_id, 1 if is_default else 0),
        )
        _db().commit()


def remove_namespace(namespace: str) -> None:
    """Remove a namespace. Its grants cascade away."""
    with _lock:
        _db().execute("DELETE FROM project_namespaces WHERE namespace = ?", (namespace,))
        _db().commit()


# --------------------------------------------------------------------------- #
# Ownership
# --------------------------------------------------------------------------- #
def owners_of(project_id: str) -> List[dict]:
    rows = _db().execute(
        "SELECT user_id, username FROM project_owners WHERE project_id = ? ORDER BY username",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def owned_project_ids(user_id: str) -> Set[str]:
    if not user_id:
        return set()
    rows = _db().execute(
        "SELECT project_id FROM project_owners WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {r["project_id"] for r in rows}


def is_owner(user_id: str, project_id: str) -> bool:
    if not user_id:
        return False
    row = _db().execute(
        "SELECT 1 FROM project_owners WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    return row is not None


def add_owner(project_id: str, user_id: str, username: str = "") -> None:
    with _lock:
        _db().execute(
            "INSERT INTO project_owners (project_id, user_id, username) VALUES (?,?,?) "
            "ON CONFLICT(project_id, user_id) DO UPDATE SET username = excluded.username",
            (project_id, user_id, username),
        )
        _db().commit()


def remove_owner(project_id: str, user_id: str) -> None:
    with _lock:
        _db().execute(
            "DELETE FROM project_owners WHERE project_id = ? AND user_id = ?",
            (project_id, user_id),
        )
        _db().commit()


# --------------------------------------------------------------------------- #
# Source repos (self-service Argo CD AppProject.sourceRepos management)
# --------------------------------------------------------------------------- #
def source_repos_of(project_id: str) -> List[str]:
    rows = _db().execute(
        "SELECT repo_url FROM project_source_repos WHERE project_id = ? ORDER BY repo_url",
        (project_id,),
    ).fetchall()
    return [r["repo_url"] for r in rows]


def source_repos_detail_of(project_id: str) -> List[dict]:
    """Each of the project's own repos with its GitHub App connection state:
    [{repo_url, installation_id}]. installation_id '' means not connected."""
    rows = _db().execute(
        "SELECT repo_url, installation_id FROM project_source_repos "
        "WHERE project_id = ? ORDER BY repo_url",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_source_repo(project_id: str, repo_url: str) -> None:
    with _lock:
        _db().execute(
            "INSERT OR IGNORE INTO project_source_repos (project_id, repo_url) VALUES (?,?)",
            (project_id, repo_url),
        )
        _db().commit()


def remove_source_repo(project_id: str, repo_url: str) -> None:
    with _lock:
        _db().execute(
            "DELETE FROM project_source_repos WHERE project_id = ? AND repo_url = ?",
            (project_id, repo_url),
        )
        _db().commit()


def set_repo_installation(
    project_id: str, repo_url: str, installation_id: str, connection_id: str = ""
) -> None:
    """Record (or clear, with '') the GitHub App installation a repo was
    connected through, and which registered connection minted it. The repo must
    already exist for this project."""
    with _lock:
        _db().execute(
            "UPDATE project_source_repos SET installation_id = ?, connection_id = ? "
            "WHERE project_id = ? AND repo_url = ?",
            (installation_id, connection_id, project_id, repo_url),
        )
        _db().commit()


def connected_repos_of(project_id: str) -> List[dict]:
    """The project's repos that have been connected through a GitHub App
    (installation_id set): [{repo_url, installation_id, connection_id}]. This is
    what teams-operator needs to materialize Argo CD githubApp repo credentials
    (see /internal/teams). connection_id '' means the legacy platform App."""
    rows = _db().execute(
        "SELECT repo_url, installation_id, connection_id FROM project_source_repos "
        "WHERE project_id = ? AND installation_id != '' ORDER BY repo_url",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def repo_exists(project_id: str, repo_url: str) -> bool:
    row = _db().execute(
        "SELECT 1 FROM project_source_repos WHERE project_id = ? AND repo_url = ?",
        (project_id, repo_url),
    ).fetchone()
    return row is not None


# --- Global source-repo whitelist (admin-curated, available to every project) --
def global_source_repos() -> List[str]:
    rows = _db().execute(
        "SELECT repo_url FROM global_source_repos ORDER BY repo_url"
    ).fetchall()
    return [r["repo_url"] for r in rows]


def add_global_source_repo(repo_url: str) -> None:
    with _lock:
        _db().execute(
            "INSERT OR IGNORE INTO global_source_repos (repo_url) VALUES (?)", (repo_url,)
        )
        _db().commit()


def remove_global_source_repo(repo_url: str) -> None:
    with _lock:
        _db().execute("DELETE FROM global_source_repos WHERE repo_url = ?", (repo_url,))
        _db().commit()


# --- Pending GitHub App connections (operator resolves these; see main.py) -----
def add_github_connection(target: str, installation_id: str, connection_id: str = "") -> None:
    with _lock:
        _db().execute(
            "INSERT INTO github_connections (target, installation_id, connection_id, created_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(target, installation_id) DO UPDATE SET connection_id = excluded.connection_id",
            (target, installation_id, connection_id, datetime.now().isoformat()),
        )
        _db().commit()


def pending_github_connections() -> List[dict]:
    rows = _db().execute(
        "SELECT target, installation_id, connection_id FROM github_connections ORDER BY created_at"
    ).fetchall()
    return [dict(r) for r in rows]


def delete_github_connection(target: str, installation_id: str) -> None:
    with _lock:
        _db().execute(
            "DELETE FROM github_connections WHERE target = ? AND installation_id = ?",
            (target, installation_id),
        )
        _db().commit()


# --- Registered GitHub App connections (per-project) ---------------------------
def add_github_app_connection(
    connection_id: str, project_id: str, created_by: str, status: str = "pending"
) -> None:
    """Insert a connection row (status 'pending' until the operator resolves the
    manifest exchange). name/slug/app_id are filled in at resolve time."""
    with _lock:
        _db().execute(
            "INSERT OR IGNORE INTO github_app_connections "
            "(id, project_id, status, created_by, created_at) VALUES (?,?,?,?,?)",
            (connection_id, project_id, status, created_by, datetime.now().isoformat()),
        )
        _db().commit()


def set_github_app_connection_ready(
    connection_id: str, name: str, slug: str, app_id: str
) -> None:
    """Flip a connection to 'ready' with the App metadata the operator resolved."""
    with _lock:
        _db().execute(
            "UPDATE github_app_connections SET name = ?, slug = ?, app_id = ?, status = 'ready' "
            "WHERE id = ?",
            (name, slug, app_id, connection_id),
        )
        _db().commit()


def github_app_connections_of(project_id: str, ready_only: bool = False) -> List[dict]:
    """A project's registered GitHub App connections, newest first. When
    ready_only, omit ones still mid-registration (no App key materialized yet)."""
    q = (
        "SELECT id, project_id, name, slug, app_id, status, created_by, created_at "
        "FROM github_app_connections WHERE project_id = ?"
    )
    if ready_only:
        q += " AND status = 'ready'"
    q += " ORDER BY created_at DESC"
    return [dict(r) for r in _db().execute(q, (project_id,)).fetchall()]


def get_github_app_connection(connection_id: str) -> Optional[dict]:
    row = _db().execute(
        "SELECT id, project_id, name, slug, app_id, status, created_by, created_at "
        "FROM github_app_connections WHERE id = ?",
        (connection_id,),
    ).fetchone()
    return dict(row) if row else None


def delete_github_app_connection(connection_id: str) -> None:
    with _lock:
        _db().execute("DELETE FROM github_app_connections WHERE id = ?", (connection_id,))
        _db().commit()


# --- Pending GitHub App Manifest exchanges (operator performs the conversion) ---
def add_github_app_registration(connection_id: str, project_id: str, code: str) -> None:
    with _lock:
        _db().execute(
            "INSERT OR REPLACE INTO github_app_registrations "
            "(connection_id, project_id, code, created_at) VALUES (?,?,?,?)",
            (connection_id, project_id, code, datetime.now().isoformat()),
        )
        _db().commit()


def pending_github_app_registrations() -> List[dict]:
    rows = _db().execute(
        "SELECT connection_id, project_id, code FROM github_app_registrations ORDER BY created_at"
    ).fetchall()
    return [dict(r) for r in rows]


def delete_github_app_registration(connection_id: str) -> None:
    with _lock:
        _db().execute(
            "DELETE FROM github_app_registrations WHERE connection_id = ?", (connection_id,)
        )
        _db().commit()


def effective_source_repos(project_id: str) -> List[str]:
    """The repos the project's AppProject should allow: the project's own repos
    UNIONed with the admin global whitelist. This is what teams-operator
    reconciles into sourceRepos (see /internal/teams) — computing the union here
    means a global-whitelist change is reflected for every project on the
    operator's next poll with no operator-side global logic."""
    return sorted(set(source_repos_of(project_id)) | set(global_source_repos()))


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
                "UPDATE project_owners SET username = ? WHERE user_id = ? AND username != ?",
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

    Runs only when the database has no projects, so re-running is a no-op. This is
    what preserves everyone's existing access across the cutover: each namespace's
    Keycloak group members become grants, and members holding the legacy
    `team-leader` realm role become **owners** of the project.

    `members_of(ns) -> [username]`, `users_by_name` maps username -> Keycloak user
    (needs `id`), `leaders` is the set of usernames holding `team-leader`, and
    `default_namespace_of(project_name) -> str` identifies the non-deletable namespace.

    Returns a summary dict for logging. The JSON file is left untouched as a backup.
    """
    summary = {"teams": 0, "namespaces": 0, "owners": 0, "grants": 0, "skipped": []}

    if _db().execute("SELECT 1 FROM projects LIMIT 1").fetchone():
        return {**summary, "status": "already-migrated"}
    if not Path(json_path).exists():
        return {**summary, "status": "no-legacy-data"}

    try:
        with Path(json_path).open() as f:
            legacy = json.load(f)
    except Exception as e:  # noqa: BLE001 - a bad backup file must not block startup
        log.error("Could not read legacy store %s: %s", json_path, e)
        return {**summary, "status": "unreadable"}

    for project in legacy:
        project_id, name = project.get("id"), project.get("name")
        if not project_id or not name:
            continue
        nss = project.get("namespaces") or [default_namespace_of(name)]
        default_ns = default_namespace_of(name)

        with _lock:
            _db().execute(
                "INSERT OR IGNORE INTO projects (id, name, created_at) VALUES (?,?,?)",
                (project_id, name, project.get("created_at") or datetime.now().isoformat()),
            )
            for ns in nss:
                _db().execute(
                    "INSERT OR IGNORE INTO project_namespaces (namespace, project_id, is_default) "
                    "VALUES (?,?,?)",
                    (ns, project_id, 1 if ns == default_ns else 0),
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
                    add_owner(project_id, uid, uname)
                    summary["owners"] += 1
                else:
                    set_grant(ns, uid, uname, "viewer")
                    summary["grants"] += 1

    record("system", "migrate", "legacy-json", json.dumps(summary, default=str))
    return {**summary, "status": "migrated"}
