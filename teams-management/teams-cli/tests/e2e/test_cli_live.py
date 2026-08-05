"""Runs the REAL teams_cli.py as a subprocess against the live deployed
teams-api — catches exactly the class of bug unit tests (which mock
`requests`) can't: a URL that's simply wrong against the real API (this is
how create_team/list_teams/get_team/delete_team's stale `/teams` path — a
404 against the real `/projects` API — was actually found).

Bypasses the interactive PKCE browser `login` command: injects a token
obtained via direct Keycloak password grant (the `teams-e2e-tests` client;
see platform-infra/apps/security/keycloak) into the same tokens.json file
`teams-cli login` would have written, in an isolated XDG_CONFIG_HOME so a
real user's stored CLI session is never touched.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

pytestmark = pytest.mark.e2e

TEAMS_API_URL = os.environ.get("TEAMS_API_URL", "https://teams-api.127.0.0.1.sslip.io:8443")
KEYCLOAK_ISSUER = os.environ.get(
    "KEYCLOAK_ISSUER", "https://platform-auth.127.0.0.1.sslip.io:8443/auth/realms/teams"
)
E2E_CLIENT_SECRET = os.environ.get("E2E_CLIENT_SECRET", "dev-teams-e2e-tests-secret-change-me")
CLI = Path(__file__).resolve().parent.parent.parent / "teams_cli.py"


@pytest.fixture
def cli_env(tmp_path):
    resp = requests.post(
        f"{KEYCLOAK_ISSUER}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "teams-e2e-tests",
            "client_secret": E2E_CLIENT_SECRET,
            "username": "admin",
            "password": "admin123",
        },
        verify=False,
        timeout=10,
    )
    resp.raise_for_status()
    tok = resp.json()

    config_home = tmp_path / "xdg-config"
    (config_home / "teams-cli").mkdir(parents=True)
    (config_home / "teams-cli" / "tokens.json").write_text(
        json.dumps(
            {
                "access_token": tok["access_token"],
                "refresh_token": tok.get("refresh_token"),
                "id_token": tok.get("id_token", tok["access_token"]),
                "expires_at": time.time() + int(tok.get("expires_in", 300)),
                "auth_url": KEYCLOAK_ISSUER.rsplit("/realms/", 1)[0],
                "realm": "teams",
                "client": "teams-e2e-tests",
            }
        )
    )

    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = str(config_home)
    env["TEAMS_API_URL"] = TEAMS_API_URL
    return env


def run_cli(*args, env):
    return subprocess.run(
        [sys.executable, str(CLI), "--insecure", *args], capture_output=True, text=True, env=env, timeout=30
    )


def test_health(cli_env):
    result = run_cli("health", env=cli_env)
    assert result.returncode == 0, result.stderr
    assert "API Status" in result.stdout


def test_create_list_get_delete_roundtrip(cli_env):
    name = f"clie2e{int(time.time())}"

    created = run_cli("create", name, env=cli_env)
    assert created.returncode == 0, created.stderr
    assert "Created team" in created.stdout
    project_id = next(line for line in created.stdout.splitlines() if "Team ID" in line).split()[-1]

    listed = run_cli("list", env=cli_env)
    assert name in listed.stdout

    got = run_cli("get", project_id, env=cli_env)
    assert got.returncode == 0, got.stderr
    assert name in got.stdout

    deleted = run_cli("delete", project_id, env=cli_env)
    assert deleted.returncode == 0, deleted.stderr
    assert "deleted successfully" in deleted.stdout

    listed_after = run_cli("list", env=cli_env)
    assert name not in listed_after.stdout
