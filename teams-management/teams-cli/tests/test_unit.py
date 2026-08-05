"""Unit tests: pure helpers + TeamsAPI with requests mocked (no network, no
live cluster). Import path mirrors teams-api's tests/conftest.py pattern
(sys.path insert, since teams-cli has no package structure)."""
import base64
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import teams_cli  # noqa: E402


def test_pkce_pair_is_s256_of_the_verifier():
    verifier, challenge = teams_cli._pkce_pair()

    assert 43 <= len(verifier) <= 128  # RFC 7636 code_verifier length bounds
    import hashlib

    expected = teams_cli._b64url(hashlib.sha256(verifier.encode()).digest())
    assert challenge == expected


def test_pkce_pair_is_random_each_call():
    v1, _ = teams_cli._pkce_pair()
    v2, _ = teams_cli._pkce_pair()
    assert v1 != v2


def test_b64url_no_padding_and_urlsafe():
    raw = bytes(range(256))
    encoded = teams_cli._b64url(raw)

    assert "=" not in encoded
    assert "+" not in encoded and "/" not in encoded
    # Round-trips through standard base64url decoding once padding is restored.
    padded = encoded + "=" * (-len(encoded) % 4)
    assert base64.urlsafe_b64decode(padded) == raw


def test_decode_jwt_claims_reads_the_payload_without_verifying_signature():
    payload = {"preferred_username": "teamlead1", "realm_access": {"roles": ["admin"]}}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    fake_token = f"header.{payload_b64}.signature"

    assert teams_cli._decode_jwt_claims(fake_token) == payload


def test_decode_jwt_claims_returns_empty_dict_on_garbage():
    assert teams_cli._decode_jwt_claims("not-a-jwt") == {}
    assert teams_cli._decode_jwt_claims("") == {}


@pytest.fixture
def api():
    a = teams_cli.TeamsAPI(base_url="https://teams-api.example.test", verify=True)
    a._access_token = MagicMock(return_value="fake-token")
    return a


class TestTeamsAPIProjectEndpoints:
    """Regression tests: these methods used to call the pre-rename `/teams`
    path, which 404s against the real (Projects) teams-api — found live
    while writing this suite, fixed alongside it."""

    def test_create_team_posts_to_projects(self, api):
        with patch("teams_cli.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200, json=lambda: {"name": "n", "id": "1", "created_at": "t"}
            )
            api.create_team("n")
            url = mock_post.call_args[0][0]
            assert url == "https://teams-api.example.test/projects"

    def test_list_teams_gets_projects(self, api):
        with patch("teams_cli.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
            api.list_teams()
            url = mock_get.call_args[0][0]
            assert url == "https://teams-api.example.test/projects"

    def test_get_team_gets_projects_id(self, api):
        with patch("teams_cli.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: {"name": "n", "id": "1", "created_at": "t"}
            )
            api.get_team("1")
            url = mock_get.call_args[0][0]
            assert url == "https://teams-api.example.test/projects/1"

    def test_delete_team_deletes_projects_id(self, api):
        with patch("teams_cli.requests.delete") as mock_delete:
            mock_delete.return_value = MagicMock(status_code=200, json=lambda: {"message": "ok"})
            api.delete_team("1")
            url = mock_delete.call_args[0][0]
            assert url == "https://teams-api.example.test/projects/1"


def test_health_check_hits_health_endpoint(api):
    with patch("teams_cli.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"status": "ok", "teams_count": 3})
        api.health_check()
        url = mock_get.call_args[0][0]
        assert url == "https://teams-api.example.test/health"
