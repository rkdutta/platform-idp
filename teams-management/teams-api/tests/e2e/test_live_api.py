"""Black-box tests against the LIVE deployed teams-api (not the in-process
TestClient the rest of tests/ uses). Needs a reachable cluster and Keycloak.

Authenticates via the `teams-e2e-tests` Keycloak client (password grant) —
a test-only client added specifically because neither `teams-ui` nor
`teams-cli` has directAccessGrantsEnabled, by design (see
platform-infra/apps/security/keycloak/application.yaml). Demo credentials
only; never used against a real deployment.
"""
import os

import pytest
import requests

pytestmark = pytest.mark.e2e

TEAMS_API_URL = os.environ.get("TEAMS_API_URL", "https://teams-api.127.0.0.1.sslip.io:8443")
KEYCLOAK_ISSUER = os.environ.get(
    "KEYCLOAK_ISSUER", "https://platform-auth.127.0.0.1.sslip.io:8443/auth/realms/teams"
)
E2E_CLIENT_SECRET = os.environ.get("E2E_CLIENT_SECRET", "dev-teams-e2e-tests-secret-change-me")


def _token(username: str, password: str) -> str:
    resp = requests.post(
        f"{KEYCLOAK_ISSUER}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "teams-e2e-tests",
            "client_secret": E2E_CLIENT_SECRET,
            "username": username,
            "password": password,
        },
        verify=False,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def teamlead_token():
    return _token("teamlead1", "password123")


def test_root_health():
    resp = requests.get(f"{TEAMS_API_URL}/", verify=False, timeout=10)
    assert resp.status_code == 200
    assert "Teams API" in resp.json().get("message", "")


@pytest.mark.parametrize("path", ["/projects", "/kubeconfig", "/me"])
def test_unauthenticated_requests_rejected(path):
    resp = requests.get(f"{TEAMS_API_URL}{path}", verify=False, timeout=10)
    assert resp.status_code == 401


def test_authenticated_me(teamlead_token):
    resp = requests.get(
        f"{TEAMS_API_URL}/me", headers={"Authorization": f"Bearer {teamlead_token}"}, verify=False, timeout=10
    )
    assert resp.status_code == 200
    assert resp.json().get("username") == "teamlead1"


def test_authenticated_projects_roundtrip(teamlead_token):
    resp = requests.get(
        f"{TEAMS_API_URL}/projects", headers={"Authorization": f"Bearer {teamlead_token}"}, verify=False, timeout=10
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_authenticated_kubeconfig(teamlead_token):
    resp = requests.get(
        f"{TEAMS_API_URL}/kubeconfig", headers={"Authorization": f"Bearer {teamlead_token}"}, verify=False, timeout=10
    )
    assert resp.status_code == 200
    assert "clusters:" in resp.text
