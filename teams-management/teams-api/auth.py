"""JWT authentication/authorization for the Teams API.

Validates Keycloak-issued access tokens (RS256) against the realm's JWKS:
signature, issuer, and expiry. Used as an app-level FastAPI dependency so every
route is protected except the public ones (health/root/docs).

This module answers only "who is calling?". *What they may do* is resolved in
authz.py from the database (project ownership + per-namespace roles) — the single
exception being the `admin` realm role, which stays in the token because it is
the bootstrap authority that grants everything else.

Both the Angular UI (client `teams-ui`) and the CLI (client `teams-cli`) get
tokens from the same `teams` realm, so a single issuer + JWKS validates both.

Config (env):
  AUTH_ENABLED     "true"/"false" — master switch (default true)
  OIDC_ISSUER      expected `iss` claim (the realm's public URL)
  OIDC_JWKS_URL    where to fetch signing keys (in-cluster: internal HTTP svc)
  OIDC_TLS_VERIFY  verify TLS when fetching JWKS (default true; set false only
                   if pointing JWKS at a self-signed HTTPS endpoint)
"""

from __future__ import annotations

import json
import logging
import os
import time

import jwt
import requests
from fastapi import HTTPException, Request
from jwt.algorithms import RSAAlgorithm

log = logging.getLogger("teams-api.auth")


def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


AUTH_ENABLED = _flag("AUTH_ENABLED", "true")
OIDC_ISSUER = os.getenv(
    "OIDC_ISSUER",
    "https://platform-auth.127.0.0.1.sslip.io:8443/auth/realms/teams",
)
OIDC_JWKS_URL = os.getenv(
    "OIDC_JWKS_URL",
    "http://keycloak-keycloakx-http.keycloak.svc/auth/realms/teams/protocol/openid-connect/certs",
)
OIDC_TLS_VERIFY = _flag("OIDC_TLS_VERIFY", "true")
JWKS_CACHE_TTL = int(os.getenv("OIDC_JWKS_CACHE_TTL", "3600"))

# The confidential client teams-operator authenticates as (client-credentials
# grant) to call this API's /internal/* control-plane endpoints - see
# require_operator. Replaces the previous fully-open /internal/* design.
OPERATOR_CLIENT_ID = os.getenv("OPERATOR_CLIENT_ID", "teams-operator-sa")

# Paths served without authentication (probes, root, API docs).
# /github/callback is public because GitHub redirects the user's browser to it
# with no bearer token — it authenticates the request by verifying the signed
# `state` it issued at /github/install-url instead (see main.py). Everything
# else stays protected.
PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json", "/github/callback"}

# Cache of kid -> public key, refreshed on TTL or on an unknown kid (rotation).
_jwks: dict = {"keys": {}, "fetched_at": 0.0}


def _refresh_keys() -> None:
    resp = requests.get(OIDC_JWKS_URL, verify=OIDC_TLS_VERIFY, timeout=10)
    resp.raise_for_status()
    _jwks["keys"] = {
        k["kid"]: RSAAlgorithm.from_jwk(json.dumps(k)) for k in resp.json()["keys"]
    }
    _jwks["fetched_at"] = time.time()


def _signing_key(kid: str):
    stale = time.time() - _jwks["fetched_at"] > JWKS_CACHE_TTL
    if kid not in _jwks["keys"] or stale:
        _refresh_keys()
    if kid not in _jwks["keys"]:  # possible key rotation since last fetch
        _refresh_keys()
    return _jwks["keys"].get(kid)


def _decode(token: str) -> dict:
    kid = jwt.get_unverified_header(token).get("kid")
    key = _signing_key(kid)
    if key is None:
        raise jwt.InvalidTokenError("no matching signing key (kid)")
    # Keycloak's default access-token audience is "account", so we don't pin aud;
    # signature + issuer + expiry are what gate access here.
    return jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        issuer=OIDC_ISSUER,
        options={"verify_aud": False, "require": ["exp", "iss"]},
    )


def _roles(claims: dict) -> list[str]:
    return list(claims.get("realm_access", {}).get("roles", []))


# `admin` is the only realm role this API still reads. The legacy `team-leader`
# and `viewer` realm roles are superseded by DB-held project ownership and
# per-namespace grants (see store.py / authz.py); they remain defined in the realm
# but no longer carry any authority here.


def _is_public(request: Request) -> bool:
    """Paths served without auth: probes, root, docs, CORS preflight.

    /internal/* is deliberately NOT here — those control-plane endpoints
    return unscoped, cluster-wide data (every project, all namespace grants),
    so they require a real bearer token same as any other route; see
    require_operator for the additional check that it specifically belongs
    to teams-operator's own teams-operator-sa client, not just any
    authenticated realm user.
    """
    if request.method == "OPTIONS":  # preflight carries no Authorization
        return True
    path = request.url.path
    return (
        path in PUBLIC_PATHS
        or path.startswith("/docs")
        or path.startswith("/openapi")
    )


async def authenticate(request: Request) -> None:
    """App-level dependency: require a valid bearer token on non-public paths and
    stash the verified claims on request.state for downstream role checks."""
    if not AUTH_ENABLED or _is_public(request):
        return

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed bearer token")
    token = header.split(" ", 1)[1].strip()
    try:
        claims = _decode(token)
    except requests.RequestException as e:  # JWKS unreachable
        log.error("JWKS fetch failed: %s", e)
        raise HTTPException(status_code=503, detail="Auth backend unavailable")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    request.state.claims = claims
    request.state.username = claims.get("preferred_username")
    # The Keycloak `sub` is the stable identity every authorization record is
    # keyed on. Usernames are mutable in Keycloak and would silently re-point a
    # grant, so they are only ever carried for display.
    request.state.user_id = claims.get("sub")


def require_read(request: Request) -> None:
    """App-level dependency (runs after authenticate): the caller must be a valid
    realm user.

    Authorization proper is no longer a realm role — it lives in the database
    (project ownership + per-namespace viewer/maintainer grants, see authz.py). A
    user with no grants authenticates fine and simply sees nothing, so there is
    nothing left for a coarse read-role gate to add.
    """
    if not AUTH_ENABLED or _is_public(request):
        return
    if not getattr(request.state, "claims", None):
        raise HTTPException(status_code=401, detail="Authentication required")


def require_admin(request: Request) -> None:
    """Route dependency for platform administration (project lifecycle, ownership).

    `admin` stays a REALM role deliberately: it is the bootstrap authority that
    hands out every DB-held permission, so it must not itself be DB-held —
    otherwise a bad migration could leave nobody able to repair the system.
    """
    if not AUTH_ENABLED:
        return
    claims = getattr(request.state, "claims", None) or {}
    if "admin" not in _roles(claims):
        raise HTTPException(
            status_code=403,
            detail="Requires the 'admin' realm role",
        )


def is_admin(request: Request) -> bool:
    """True if the caller holds the `admin` realm role (or auth is disabled)."""
    if not AUTH_ENABLED:
        return True
    claims = getattr(request.state, "claims", None) or {}
    return "admin" in _roles(claims)


def is_project_manager(request: Request) -> bool:
    """True if the caller holds the `project-manager` realm role (or auth disabled).

    A global capability - "may create a project" - not scoped to any one
    project, unlike DB-held ownership of a specific project (store.is_owner),
    which is what lets them manage the ones they hold after creation. Kept as
    a realm role (like `admin`) rather than a DB row for the same reason
    require_admin's docstring gives for `admin`: bootstrap authority for a
    capability shouldn't itself live in the store it grants access to.
    """
    if not AUTH_ENABLED:
        return True
    claims = getattr(request.state, "claims", None) or {}
    return "project-manager" in _roles(claims)


def require_admin_or_project_manager(request: Request) -> None:
    """Route dependency for self-service project creation: admins and anyone
    holding the `project-manager` realm role (see is_project_manager)."""
    if not AUTH_ENABLED:
        return
    claims = getattr(request.state, "claims", None) or {}
    if "admin" not in _roles(claims) and "project-manager" not in _roles(claims):
        raise HTTPException(
            status_code=403,
            detail="Requires the 'admin' or 'project-manager' realm role",
        )


def require_operator(request: Request) -> None:
    """Route dependency for the /internal/* control-plane endpoints:
    requires a valid bearer token whose `azp` (authorized party) is
    teams-operator's own confidential client (client-credentials grant, no
    user behind it) - not just any authenticated realm user, since these
    endpoints return unscoped, cluster-wide data. `authenticate` (the global
    app dependency) already validated the token and populated
    request.state.claims by the time this runs.
    """
    if not AUTH_ENABLED:
        return
    claims = getattr(request.state, "claims", None) or {}
    if claims.get("azp") != OPERATOR_CLIENT_ID:
        raise HTTPException(
            status_code=403,
            detail="Requires the teams-operator service identity",
        )


def caller_id(request: Request) -> str:
    """The caller's Keycloak `sub` — the key every grant/ownership row uses."""
    return getattr(request.state, "user_id", None) or ""


def caller_name(request: Request) -> str:
    """The caller's username, for audit rows and display only."""
    return getattr(request.state, "username", None) or ""
