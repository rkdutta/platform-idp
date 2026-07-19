"""JWT authentication/authorization for the Teams API.

Validates Keycloak-issued access tokens (RS256) against the realm's JWKS:
signature, issuer, and expiry. Used as an app-level FastAPI dependency so every
route is protected except the public ones (health/root/docs).

This module answers only "who is calling?". *What they may do* is resolved in
authz.py from the database (team ownership + per-namespace roles) — the single
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

# Paths served without authentication (probes, root, API docs).
PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}

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
# and `viewer` realm roles are superseded by DB-held team ownership and
# per-namespace grants (see store.py / authz.py); they remain defined in the realm
# but no longer carry any authority here.


def _is_public(request: Request) -> bool:
    """Paths served without auth: probes, root, docs, CORS preflight, and the
    /internal/* control-plane endpoints (consumed in-cluster by the teams-operator,
    which has no user token — restrict via NetworkPolicy)."""
    if request.method == "OPTIONS":  # preflight carries no Authorization
        return True
    path = request.url.path
    return (
        path in PUBLIC_PATHS
        or path.startswith("/docs")
        or path.startswith("/openapi")
        or path.startswith("/internal/")
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
    (team ownership + per-namespace viewer/maintainer grants, see authz.py). A
    user with no grants authenticates fine and simply sees nothing, so there is
    nothing left for a coarse read-role gate to add.
    """
    if not AUTH_ENABLED or _is_public(request):
        return
    if not getattr(request.state, "claims", None):
        raise HTTPException(status_code=401, detail="Authentication required")


def require_admin(request: Request) -> None:
    """Route dependency for platform administration (team lifecycle, ownership).

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


def caller_id(request: Request) -> str:
    """The caller's Keycloak `sub` — the key every grant/ownership row uses."""
    return getattr(request.state, "user_id", None) or ""


def caller_name(request: Request) -> str:
    """The caller's username, for audit rows and display only."""
    return getattr(request.state, "username", None) or ""
