"""JWT authentication/authorization for the Teams API.

Validates Keycloak-issued access tokens (RS256) against the realm's JWKS:
signature, issuer, and expiry. Used as an app-level FastAPI dependency so every
route is protected except the public ones (health/root/docs). Writes additionally
require the `team-leader` realm role.

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


async def authenticate(request: Request) -> None:
    """App-level dependency: require a valid bearer token on non-public paths and
    stash the verified claims on request.state for downstream role checks."""
    if not AUTH_ENABLED:
        return
    if request.method == "OPTIONS":  # CORS preflight carries no Authorization
        return
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/openapi"):
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


def require_team_leader(request: Request) -> None:
    """Route dependency for write operations: require the `team-leader` role."""
    if not AUTH_ENABLED:
        return
    claims = getattr(request.state, "claims", None) or {}
    if "team-leader" not in _roles(claims):
        raise HTTPException(
            status_code=403,
            detail="Requires the 'team-leader' realm role",
        )


def namespace_scope(request: Request):
    """Namespaces the caller is allowed to see.

    Returns None for UNRESTRICTED access (the `admin` realm role, or auth
    disabled) — the caller sees everything. Otherwise returns the set of
    namespace names taken from the token's `groups` claim (each Keycloak group
    is named after the namespace it grants). An empty set means the caller can
    see nothing. Team leads are members of exactly their team's group.
    """
    if not AUTH_ENABLED:
        return None
    claims = getattr(request.state, "claims", None) or {}
    if "admin" in _roles(claims):
        return None
    return {g.lstrip("/") for g in (claims.get("groups") or [])}
