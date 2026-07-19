"""Test fixtures for the teams-api RBAC suite.

DATA_DIR is redirected to a temp directory *before* main/store are imported, so a
test run can never touch a real /data volume.
"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="teams-api-test-"))
os.environ.setdefault("AUTH_ENABLED", "true")
# No Keycloak in unit tests: KeycloakAdmin.enabled is False without a secret, so
# the directory lookups degrade to "unknown user" rather than making network calls.
os.environ.pop("KC_ADMIN_CLIENT_SECRET", None)

import store  # noqa: E402


@pytest.fixture
def db(tmp_path):
    """A fresh SQLite store per test."""
    store.close()
    store.connect(tmp_path / "teams.db")
    yield store
    store.close()


def make_request(user_id="", username="", roles=()):
    """A stand-in for a FastAPI Request carrying verified JWT claims.

    auth.py only ever reads request.state, so this is enough to drive the real
    authorization code paths without minting tokens.
    """
    return SimpleNamespace(
        state=SimpleNamespace(
            claims={"realm_access": {"roles": list(roles)}, "sub": user_id},
            user_id=user_id,
            username=username,
        )
    )


@pytest.fixture
def admin():
    return make_request("admin-id", "admin", roles=["admin"])


@pytest.fixture
def alice():
    """A plain user — authority comes only from what the DB grants her."""
    return make_request("alice-id", "alice")


@pytest.fixture
def bob():
    return make_request("bob-id", "bob")
