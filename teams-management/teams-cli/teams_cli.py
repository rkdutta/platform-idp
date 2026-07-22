#!/usr/bin/env python3
"""
Teams CLI - A simple command-line interface for the Teams API
"""

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional

import requests
import urllib3

# Default API base URL, overridable (in precedence order) by the --url flag or
# the TEAMS_API_URL environment variable.
ENV_URL_VAR = "TEAMS_API_URL"
DEFAULT_API_BASE_URL = "http://teams-api.127.0.0.1.sslip.io"
API_BASE_URL = os.environ.get(ENV_URL_VAR, DEFAULT_API_BASE_URL)

# --- Keycloak / OIDC login config (Authorization Code + PKCE, loopback) -------
# All overridable by environment so the same CLI works against other realms.
AUTH_URL = os.environ.get("TEAMS_AUTH_URL", "https://platform-auth.127.0.0.1.sslip.io:8443/auth")
AUTH_REALM = os.environ.get("TEAMS_AUTH_REALM", "teams")
AUTH_CLIENT = os.environ.get("TEAMS_AUTH_CLIENT", "teams-cli")
# The loopback redirect must match one registered on the teams-cli client.
REDIRECT_PORT = int(os.environ.get("TEAMS_AUTH_REDIRECT_PORT", "8400"))
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

# Stored token location (0600). Honors XDG_CONFIG_HOME.
TOKEN_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "teams-cli"
TOKEN_FILE = TOKEN_DIR / "tokens.json"


def _oidc(auth_url: str, realm: str, endpoint: str) -> str:
    return f"{auth_url}/realms/{realm}/protocol/openid-connect/{endpoint}"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def _decode_jwt_claims(token: str) -> dict:
    """Decode a JWT payload WITHOUT verifying the signature (display only —
    the API is responsible for real verification)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # pad base64url
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Catches the single browser redirect to /callback and stashes its query."""

    result: dict = {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        _CallbackHandler.result = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        ok = "code" in _CallbackHandler.result
        msg = ("Login successful — you can close this tab and return to the terminal."
               if ok else "Login failed — see the terminal.")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            f"<html><body style='font-family:sans-serif;text-align:center;margin-top:3rem'>"
            f"<h3>{msg}</h3></body></html>".encode()
        )

    def log_message(self, *args):  # silence the default stderr logging
        pass

class TeamsAPI:
    def __init__(self, base_url: str = API_BASE_URL, verify: bool = True):
        self.base_url = base_url
        self.verify = verify
        if not verify:
            # Self-signed certificates: skip verification and silence the
            # per-request InsecureRequestWarning so output stays readable.
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _make_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> dict:
        """Make HTTP request to the API"""
        url = f"{self.base_url}{endpoint}"
        # Attach the bearer token if the user has logged in (see `login`).
        headers = {"Content-Type": "application/json"}
        token = self._access_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, verify=self.verify)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers, verify=self.verify)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, verify=self.verify)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.SSLError as e:
            print(f"❌ TLS Error: certificate verification failed for {self.base_url}")
            print("   If this is a self-signed certificate, re-run with --insecure (-k).")
            print(f"   ({e})")
            sys.exit(1)
        except requests.exceptions.ConnectionError:
            print(f"❌ Error: Could not connect to API at {self.base_url}")
            print("   Make sure the Teams API is running")
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            if response.status_code == 400:
                error_detail = response.json().get("detail", "Bad request")
                print(f"❌ Error: {error_detail}")
            elif response.status_code in (401, 403):
                print(f"❌ Not authorized ({response.status_code}). Your session may be "
                      "missing or expired — run `teams-cli login`.")
            elif response.status_code == 404:
                print("❌ Error: Team not found")
            else:
                print(f"❌ HTTP Error {response.status_code}: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            sys.exit(1)

    def health_check(self):
        """Check API health"""
        result = self._make_request("GET", "/health")
        status = result.get("status", "unknown")
        teams_count = result.get("teams_count", 0)
        print(f"✅ API Status: {status}")
        print(f"📊 Teams Count: {teams_count}")

    def create_team(self, name: str):
        """Create a new team"""
        result = self._make_request("POST", "/teams", {"name": name})
        print(f"✅ Created team: {result['name']}")
        print(f"🆔 Team ID: {result['id']}")
        print(f"📅 Created: {result['created_at']}")

    def list_teams(self):
        """List all teams"""
        teams = self._make_request("GET", "/teams")
        if not teams:
            print("📭 No teams found")
            return
            
        print(f"📋 Found {len(teams)} team(s):")
        print("-" * 60)
        for team in teams:
            print(f"🏷️  Name: {team['name']}")
            print(f"🆔 ID: {team['id']}")
            print(f"📅 Created: {team['created_at']}")
            print("-" * 60)

    def get_team(self, team_id: str):
        """Get a specific team by ID"""
        team = self._make_request("GET", f"/teams/{team_id}")
        print(f"🏷️  Name: {team['name']}")
        print(f"🆔 ID: {team['id']}")
        print(f"📅 Created: {team['created_at']}")

    def delete_team(self, team_id: str):
        """Delete a team"""
        result = self._make_request("DELETE", f"/teams/{team_id}")
        print(f"✅ {result['message']}")

    # --- Authentication (OAuth2 Authorization Code + PKCE, loopback) ----------

    def _save_tokens(self, tok: dict):
        """Persist tokens (0600) plus the auth context needed to refresh."""
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token"),
            "id_token": tok.get("id_token"),
            "expires_at": time.time() + int(tok.get("expires_in", 0)),
            "auth_url": AUTH_URL,
            "realm": AUTH_REALM,
            "client": AUTH_CLIENT,
        }
        TOKEN_FILE.write_text(json.dumps(data))
        os.chmod(TOKEN_FILE, 0o600)

    def _ensure_fresh_tokens(self) -> Optional[dict]:
        """Return the stored token set, refreshing it first if it's expired (or
        nearly). Returns None when the user hasn't logged in. Shared by
        _access_token() (bearer auth for the Teams API) and _id_token() (what
        k8s's OIDC authenticator actually validates — see k8s-token below)."""
        if not TOKEN_FILE.exists():
            return None
        data = json.loads(TOKEN_FILE.read_text())
        if time.time() < data.get("expires_at", 0) - 30:
            return data
        # Expired (or nearly): try a refresh_token grant.
        if data.get("refresh_token"):
            try:
                resp = requests.post(
                    _oidc(data["auth_url"], data["realm"], "token"),
                    data={"grant_type": "refresh_token", "client_id": data["client"],
                          "refresh_token": data["refresh_token"]},
                    verify=self.verify, timeout=15,
                )
                if resp.status_code == 200:
                    self._save_tokens(resp.json())
                    return json.loads(TOKEN_FILE.read_text())
            except requests.exceptions.RequestException:
                pass
        return data  # possibly stale; the caller (API or kubectl) will reject it

    def _access_token(self) -> Optional[str]:
        """A usable access token (bearer auth for the Teams API), refreshing
        first if needed. Returns None when the user hasn't logged in."""
        data = self._ensure_fresh_tokens()
        return data.get("access_token") if data else None

    def _id_token(self) -> Optional[str]:
        """A usable id_token — what k8s's OIDC authenticator validates, not the
        access_token (see k8s-token below). Returns None when the user hasn't
        logged in."""
        data = self._ensure_fresh_tokens()
        return data.get("id_token") if data else None

    def login(self, no_browser: bool = False):
        """Browser login via Authorization Code + PKCE (S256) with a loopback
        redirect. Opens the Keycloak login page, catches the redirect locally,
        exchanges the code for tokens, and stores them."""
        verifier, challenge = _pkce_pair()
        state = _b64url(secrets.token_bytes(16))
        params = urllib.parse.urlencode({
            "client_id": AUTH_CLIENT,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": REDIRECT_URI,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        })
        auth_url = f"{_oidc(AUTH_URL, AUTH_REALM, 'auth')}?{params}"

        try:
            server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
        except OSError as e:
            print(f"❌ Could not bind {REDIRECT_URI} ({e}).")
            print(f"   Is another login in progress, or is port {REDIRECT_PORT} in use?")
            sys.exit(1)
        server.timeout = 180
        _CallbackHandler.result = {}

        print(f"🔐 Logging in to realm '{AUTH_REALM}' as client '{AUTH_CLIENT}'...")
        opened = (not no_browser) and webbrowser.open(auth_url)
        if opened:
            print(f"   Browser opened. If it didn't, visit:\n   {auth_url}")
        else:
            print(f"   Open this URL in your browser to log in:\n   {auth_url}")
        print(f"   Waiting for the redirect on {REDIRECT_URI} ...")

        start = time.time()
        while not _CallbackHandler.result and time.time() - start < server.timeout:
            server.handle_request()
        server.server_close()

        res = _CallbackHandler.result
        if not res:
            print("❌ Timed out waiting for the browser login.")
            sys.exit(1)
        if res.get("state") != state:
            print("❌ State mismatch — aborting (possible CSRF).")
            sys.exit(1)
        if "code" not in res:
            print(f"❌ Login failed: {res.get('error_description', res.get('error', 'no code returned'))}")
            sys.exit(1)

        try:
            resp = requests.post(
                _oidc(AUTH_URL, AUTH_REALM, "token"),
                data={"grant_type": "authorization_code", "client_id": AUTH_CLIENT,
                      "code": res["code"], "redirect_uri": REDIRECT_URI,
                      "code_verifier": verifier},
                verify=self.verify, timeout=15,
            )
        except requests.exceptions.SSLError:
            print("❌ TLS error reaching Keycloak. For a self-signed cert, re-run with --insecure (-k).")
            sys.exit(1)
        if resp.status_code != 200:
            print(f"❌ Token exchange failed: {resp.status_code} {resp.text}")
            sys.exit(1)

        self._save_tokens(resp.json())
        claims = _decode_jwt_claims(resp.json()["access_token"])
        print(f"✅ Logged in as {claims.get('preferred_username', '?')}")
        print(f"   roles: {claims.get('realm_access', {}).get('roles', [])}")
        print(f"   token stored at {TOKEN_FILE}")

    def logout(self):
        """Remove the stored token."""
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
            print("👋 Logged out (stored token removed).")
        else:
            print("Not logged in — nothing to remove.")

    def whoami(self):
        """Show the logged-in user and token status from the stored token."""
        if not TOKEN_FILE.exists():
            print("Not logged in. Run: teams-cli login")
            return
        data = json.loads(TOKEN_FILE.read_text())
        claims = _decode_jwt_claims(data["access_token"])
        remaining = int(data.get("expires_at", 0) - time.time())
        print(f"👤 user:  {claims.get('preferred_username', '?')}")
        print(f"📧 email: {claims.get('email', '-')}")
        print(f"🎭 roles: {claims.get('realm_access', {}).get('roles', [])}")
        print(f"🏰 realm: {data.get('realm')}  (client: {data.get('client')})")
        if remaining > 0:
            print(f"⏱️  access token valid for ~{remaining}s")
        else:
            print("⏱️  access token expired (auto-refreshes on next API call)")

    # --- Kubernetes access (kubeconfig from teams-api + an exec credential plugin) --

    def k8s_token(self):
        """Print an ExecCredential object carrying the current id_token — the
        contract a k8s `exec:` credential plugin must fulfill on stdout. Not
        used by the kubeconfig `kubeconfig` below fetches (that one's `exec:`
        stanza calls `kubectl oidc-login` directly, doing its own PKCE login)
        — this is here as a standalone alternative for a hand-built
        kubeconfig that wants to reuse an existing `teams-cli login` session
        instead. k8s's OIDC authenticator validates the id_token, not the
        access_token used for the Teams API."""
        token = self._id_token()
        if not token:
            print("Not logged in. Run: teams-cli login", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({
            "apiVersion": "client.authentication.k8s.io/v1",
            "kind": "ExecCredential",
            "status": {"token": token},
        }))

    def kubeconfig(self, out: Optional[str] = None):
        """Fetch the ready-to-use kubeconfig teams-api serves (GET /kubeconfig)
        and write it to disk — a separate file, never the caller's default
        kubeconfig. Its `exec:` stanza is `kubectl oidc-login` (the
        int128/kubelogin plugin — must be installed separately, e.g.
        `brew install int128/kubelogin/kubelogin`), which does its own PKCE
        login against Keycloak at kubectl invocation time; it does not reuse
        teams-cli's own login session."""
        if not self._access_token():
            print("Not logged in — starting browser login first...")
            self.login()

        try:
            resp = requests.get(
                f"{self.base_url}/kubeconfig",
                headers={"Authorization": f"Bearer {self._access_token()}"},
                verify=self.verify,
            )
        except requests.exceptions.SSLError as e:
            print(f"❌ TLS Error: certificate verification failed for {self.base_url}")
            print("   If this is a self-signed certificate, re-run with --insecure (-k).")
            print(f"   ({e})")
            sys.exit(1)
        except requests.exceptions.ConnectionError:
            print(f"❌ Error: Could not connect to API at {self.base_url}")
            sys.exit(1)

        if resp.status_code != 200:
            detail = resp.text
            if resp.headers.get("content-type", "").startswith("application/json"):
                detail = resp.json().get("detail", detail)
            print(f"❌ Could not fetch kubeconfig: {resp.status_code} {detail}")
            sys.exit(1)

        out_path = Path(out) if out else (TOKEN_DIR / "kubeconfig")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(resp.text)
        os.chmod(out_path, 0o600)
        print(f"✅ Wrote kubeconfig to {out_path}")
        print(f"   export KUBECONFIG={out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Teams CLI - Manage teams via the Teams API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  teams-cli health                    # Check API health
  teams-cli create "Backend Team"     # Create a new team
  teams-cli list                      # List all teams
  teams-cli get <team-id>            # Get specific team
  teams-cli delete <team-id>         # Delete a team
  teams-cli kubeconfig               # Fetch a working kubeconfig
        """
    )
    
    parser.add_argument(
        "--url",
        default=API_BASE_URL,
        help=f"API base URL. Overrides the {ENV_URL_VAR} env var. "
             f"(env {ENV_URL_VAR} or default: {DEFAULT_API_BASE_URL})"
    )

    parser.add_argument(
        "--insecure", "-k",
        action="store_true",
        help="Skip TLS certificate verification (use for self-signed certs)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Auth commands
    login_parser = subparsers.add_parser(
        "login", help="Log in via browser (OAuth2 Authorization Code + PKCE)")
    login_parser.add_argument(
        "--no-browser", action="store_true",
        help="Print the login URL instead of opening a browser")
    subparsers.add_parser("logout", help="Remove the stored token")
    subparsers.add_parser("whoami", help="Show the logged-in user and token status")

    # Kubernetes access
    kubeconfig_parser = subparsers.add_parser(
        "kubeconfig", help="Fetch a working kubeconfig from the Teams API (logs in first if needed)")
    kubeconfig_parser.add_argument(
        "--out", help="Where to write it (default: ~/.config/teams-cli/kubeconfig)")
    subparsers.add_parser(
        "k8s-token",
        help="Print an ExecCredential with the current id_token (called by kubectl via `kubeconfig`, not run directly)")

    # Health command
    subparsers.add_parser("health", help="Check API health")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new team")
    create_parser.add_argument("name", help="Team name")
    
    # List command
    subparsers.add_parser("list", help="List all teams")
    
    # Get command
    get_parser = subparsers.add_parser("get", help="Get a specific team")
    get_parser.add_argument("team_id", help="Team ID")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a team")
    delete_parser.add_argument("team_id", help="Team ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize API client
    api = TeamsAPI(args.url, verify=not args.insecure)
    
    # Execute command
    try:
        if args.command == "login":
            api.login(no_browser=args.no_browser)
        elif args.command == "logout":
            api.logout()
        elif args.command == "whoami":
            api.whoami()
        elif args.command == "kubeconfig":
            api.kubeconfig(out=args.out)
        elif args.command == "k8s-token":
            api.k8s_token()
        elif args.command == "health":
            api.health_check()
        elif args.command == "create":
            api.create_team(args.name)
        elif args.command == "list":
            api.list_teams()
        elif args.command == "get":
            api.get_team(args.team_id)
        elif args.command == "delete":
            api.delete_team(args.team_id)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()
