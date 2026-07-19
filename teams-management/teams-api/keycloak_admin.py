"""Keycloak Admin API client for teams-api.

Keycloak is the **user directory** for teams-api: it answers "who exists" so the
API can validate an owner or grantee and populate the assignment pickers.

It is no longer an authorization store. As of 2.0.0, ownership and per-namespace
roles live in SQLite (see store.py) and are read live on every request, so access
changes take effect immediately instead of waiting for a token refresh. The group
methods below survive only because the one-time migration reads the pre-2.0 group
membership to seed that database; nothing writes groups any more.

Authenticates with the confidential `teams-api-sa` client via the client-credentials
grant. The service account holds realm-management roles (manage-users / view-users /
manage-realm) so it can create groups, list users, and edit memberships.

Config (env):
  KEYCLOAK_BASE_URL     Keycloak base incl. the `/auth` prefix used by this deploy
                        (default: internal http Service). The token + admin URLs are
                        derived from it.
  KEYCLOAK_REALM        realm name (default "teams")
  KC_ADMIN_CLIENT_ID    service-account client id (default "teams-api-sa")
  KC_ADMIN_CLIENT_SECRET  client secret (from a Kubernetes Secret)
  KC_ADMIN_TLS_VERIFY   verify TLS on Keycloak calls (default true)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict, List, Optional

import requests

log = logging.getLogger("teams-api.keycloak")

# App realm roles surfaced next to each user in the assignment picker.
APP_ROLES = ["admin", "team-leader", "viewer"]


class KeycloakAdminError(RuntimeError):
    """Raised when a Keycloak Admin API call fails (surface as 5xx to the caller)."""


def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class KeycloakAdmin:
    def __init__(self) -> None:
        # Base URL includes the `/auth` prefix this Keycloak deployment serves under
        # (matches OIDC_ISSUER `.../auth/realms/teams` in auth.py).
        self.base = os.getenv(
            "KEYCLOAK_BASE_URL",
            "http://keycloak-keycloakx-http.keycloak.svc/auth",
        ).rstrip("/")
        self.realm = os.getenv("KEYCLOAK_REALM", "teams")
        self.client_id = os.getenv("KC_ADMIN_CLIENT_ID", "teams-api-sa")
        self.client_secret = os.getenv("KC_ADMIN_CLIENT_SECRET", "")
        self.verify = _flag("KC_ADMIN_TLS_VERIFY", "true")

        self._lock = threading.Lock()
        self._token: str = ""
        self._token_exp: float = 0.0
        # name -> group id cache (groups are stable once created).
        self._group_ids: Dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        """Admin operations require a client secret; without one we no-op/degrade."""
        return bool(self.client_secret)

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #
    def _admin_url(self, path: str) -> str:
        return f"{self.base}/admin/realms/{self.realm}{path}"

    def token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_exp - 15:
                return self._token
            url = f"{self.base}/realms/{self.realm}/protocol/openid-connect/token"
            try:
                resp = requests.post(
                    url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    verify=self.verify,
                    timeout=10,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                raise KeycloakAdminError(f"token request failed: {e}") from e
            body = resp.json()
            self._token = body["access_token"]
            self._token_exp = time.time() + int(body.get("expires_in", 60))
            return self._token

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token()}"}

    def _request(self, method: str, path: str, **kw) -> requests.Response:
        try:
            resp = requests.request(
                method,
                self._admin_url(path),
                headers=self._headers(),
                verify=self.verify,
                timeout=10,
                **kw,
            )
        except requests.RequestException as e:
            raise KeycloakAdminError(f"{method} {path} failed: {e}") from e
        return resp

    # ------------------------------------------------------------------ #
    # Groups
    # ------------------------------------------------------------------ #
    def group_id(self, name: str) -> Optional[str]:
        """Resolve a top-level group's id by exact name (cached)."""
        if name in self._group_ids:
            return self._group_ids[name]
        resp = self._request("GET", "/groups", params={"search": name, "max": 100})
        if resp.status_code != 200:
            raise KeycloakAdminError(f"list groups {resp.status_code}: {resp.text}")
        for g in resp.json():
            if g.get("name") == name:
                self._group_ids[name] = g["id"]
                return g["id"]
        return None

    def ensure_group(self, name: str) -> str:
        """Create the group if missing; return its id. Idempotent (409 tolerated)."""
        gid = self.group_id(name)
        if gid:
            return gid
        resp = self._request("POST", "/groups", json={"name": name})
        if resp.status_code not in (201, 409):
            raise KeycloakAdminError(f"create group {resp.status_code}: {resp.text}")
        # Re-resolve (201 returns a Location header; simplest is to look it up).
        self._group_ids.pop(name, None)
        gid = self.group_id(name)
        if not gid:
            raise KeycloakAdminError(f"group '{name}' not found after create")
        return gid

    def delete_group(self, name: str) -> None:
        """Delete a group (idempotent). Called when a namespace is removed so its
        access group doesn't linger and re-grant old members if the namespace name
        is later reused."""
        gid = self.group_id(name)
        if not gid:
            return
        resp = self._request("DELETE", f"/groups/{gid}")
        if resp.status_code not in (204, 200, 404):
            raise KeycloakAdminError(f"delete group {resp.status_code}: {resp.text}")
        self._group_ids.pop(name, None)

    def group_members(self, name: str) -> List[str]:
        """Usernames belonging to the group (empty if the group doesn't exist)."""
        gid = self.group_id(name)
        if not gid:
            return []
        resp = self._request("GET", f"/groups/{gid}/members", params={"max": 1000})
        if resp.status_code != 200:
            raise KeycloakAdminError(f"group members {resp.status_code}: {resp.text}")
        return [u["username"] for u in resp.json() if u.get("username")]

    # ------------------------------------------------------------------ #
    # Users
    # ------------------------------------------------------------------ #
    def user_id(self, username: str) -> Optional[str]:
        resp = self._request(
            "GET", "/users", params={"username": username, "exact": "true"}
        )
        if resp.status_code != 200:
            raise KeycloakAdminError(f"find user {resp.status_code}: {resp.text}")
        for u in resp.json():
            if u.get("username") == username:
                return u["id"]
        return None

    def role_members(self, role: str) -> List[str]:
        """Usernames that hold a given realm role."""
        resp = self._request("GET", f"/roles/{role}/users", params={"max": 1000})
        if resp.status_code != 200:
            raise KeycloakAdminError(f"role users {resp.status_code}: {resp.text}")
        return [u["username"] for u in resp.json() if u.get("username")]

    def list_users(self) -> List[dict]:
        """All realm users as {id, username, firstName, lastName, email, roles}.

        `id` is the Keycloak `sub` — the stable key every ownership and access
        grant is stored against (usernames are mutable). `roles` is the subset of
        the app realm roles; only `admin` still carries authority in the API.
        """
        resp = self._request("GET", "/users", params={"max": 1000})
        if resp.status_code != 200:
            raise KeycloakAdminError(f"list users {resp.status_code}: {resp.text}")

        # Build username -> [app roles] with one query per role (3 total), rather
        # than N per-user role-mapping lookups.
        role_map: Dict[str, List[str]] = {}
        for role in APP_ROLES:
            try:
                for uname in self.role_members(role):
                    role_map.setdefault(uname, []).append(role)
            except KeycloakAdminError as e:
                log.warning("could not list members of role %s: %s", role, e)

        out = []
        for u in resp.json():
            if not u.get("username"):
                continue
            # Skip Keycloak service-account users (username service-account-*).
            if u["username"].startswith("service-account-"):
                continue
            out.append(
                {
                    "id": u.get("id", ""),
                    "username": u["username"],
                    "firstName": u.get("firstName", ""),
                    "lastName": u.get("lastName", ""),
                    "email": u.get("email", ""),
                    "roles": role_map.get(u["username"], []),
                }
            )
        return sorted(out, key=lambda u: u["username"])

    # ------------------------------------------------------------------ #
    # Membership
    # ------------------------------------------------------------------ #
    def add_user_to_group(self, username: str, group: str) -> None:
        uid = self.user_id(username)
        if not uid:
            raise KeycloakAdminError(f"user '{username}' not found")
        gid = self.ensure_group(group)
        resp = self._request("PUT", f"/users/{uid}/groups/{gid}")
        if resp.status_code not in (204, 201, 200):
            raise KeycloakAdminError(f"add to group {resp.status_code}: {resp.text}")

    def remove_user_from_group(self, username: str, group: str) -> None:
        uid = self.user_id(username)
        gid = self.group_id(group)
        if not uid or not gid:
            return  # nothing to remove
        resp = self._request("DELETE", f"/users/{uid}/groups/{gid}")
        if resp.status_code not in (204, 200):
            raise KeycloakAdminError(f"remove from group {resp.status_code}: {resp.text}")
