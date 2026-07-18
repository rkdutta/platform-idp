from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Set
import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from compliance import ComplianceChecker
from workloads import ApplicationsReader
from app_compliance import AppComplianceReader
from auth import (
    authenticate,
    require_read,
    require_admin,
    require_manage,
    namespace_scope,
    is_team_leader,
    AUTH_ENABLED,
)
from keycloak_admin import KeycloakAdmin, KeycloakAdminError

logger = logging.getLogger("teams-api")

# Where the team store is persisted. Backed by a PersistentVolume in-cluster so
# team data survives pod restarts (an in-memory store was wiped on every roll,
# which then made the operator prune the team namespaces).
DATA_DIR = os.getenv("DATA_DIR", "/data")
DATA_FILE = Path(DATA_DIR) / "teams.json"


def _sanitize(value: str) -> str:
    """Turn an arbitrary string into a DNS-1123-ish namespace segment.

    Mirrors teams-operator.sanitize_namespace_name so the API and the operator
    agree on the namespace name derived from a team name / order label.
    """
    seg = "".join(c if c.isalnum() else "-" for c in value.lower())
    seg = "-".join(filter(None, seg.split("-")))  # collapse consecutive hyphens
    return seg.strip("-")[:53].strip("-")


def default_namespace(team_name: str) -> str:
    """The namespace a team gets by default: team-<sanitized-name>."""
    return f"team-{_sanitize(team_name)}"


def ordered_namespace(team_name: str, label: str) -> str:
    """A self-service ordered namespace: team-<name>-<label>."""
    return f"team-{_sanitize(team_name)}-{_sanitize(label)}"


def load_teams() -> Dict[str, Dict]:
    """Load the persisted team store; empty if the file is missing/unreadable.

    Legacy records predate multi-namespace support and have no `namespaces`
    field — backfill it with the team's default namespace so every team always
    carries an explicit namespace list.
    """
    try:
        if DATA_FILE.exists():
            with DATA_FILE.open() as f:
                teams = json.load(f)
            store = {team["id"]: team for team in teams}
            for team in store.values():
                if not team.get("namespaces"):
                    team["namespaces"] = [default_namespace(team["name"])]
            return store
    except Exception as e:  # noqa: BLE001 - never fail startup on a bad/absent file
        logger.error(f"Could not load teams from {DATA_FILE}: {e}")
    return {}


def save_teams() -> None:
    """Persist the team store atomically (write temp file, then rename)."""
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = DATA_FILE.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(list(teams_store.values()), f, default=str)
        tmp.replace(DATA_FILE)
    except Exception as e:  # noqa: BLE001 - a persistence failure must not 500 the request
        logger.error(f"Could not save teams to {DATA_FILE}: {e}")

# Every route is guarded by `authenticate` (validates the Keycloak JWT) then
# `require_read` (caller must hold viewer/team-leader/admin); both exempt public
# paths (/, /health, docs). Writes additionally require the `team-leader` role
# (see per-route dependencies below).
app = FastAPI(
    title="Teams API",
    description="A simple API for team leads to create and manage teams",
    version="1.5.0",
    dependencies=[Depends(authenticate), Depends(require_read)],
)
logger.info("JWT authentication %s", "ENABLED" if AUTH_ENABLED else "DISABLED")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Team store, loaded from the persistent volume on startup.
teams_store: Dict[str, Dict] = load_teams()

# Compliance checker (reads Gatekeeper state from the Kubernetes API).
compliance_checker = ComplianceChecker()

# Applications reader (lists Rollouts/Deployments in each team's namespace).
# Promotion/rollout management is handled by the Argo Rollouts dashboard, so the
# portal is read-only here.
applications_reader = ApplicationsReader()

# Per-app compliance (supply-chain evidence + Gatekeeper), attached to each app.
app_compliance_reader = AppComplianceReader(compliance_checker)

# Keycloak Admin API client. Assigning a user to a namespace = adding them to the
# namespace's Keycloak group (group name == namespace), which is what puts the
# namespace in their token's `groups` claim and thus grants visibility.
keycloak = KeycloakAdmin()

# In-memory "who has access where" table: namespace -> {usernames}. This is a VIEW
# mirror of Keycloak group membership (the enforcement source of truth). It is
# hydrated from Keycloak on startup and updated on every grant/revoke. A database
# can replace it later — reads/writes go through the small helpers below.
access_store: Dict[str, Set[str]] = {}


def _all_namespaces() -> Set[str]:
    """Every namespace declared by any team (desired state, from the store)."""
    out: Set[str] = set()
    for team in teams_store.values():
        out.update(team.get("namespaces") or [])
    return out


def _team_for_namespace(namespace: str) -> Optional[dict]:
    """The team that owns a namespace, or None."""
    for team in teams_store.values():
        if namespace in (team.get("namespaces") or []):
            return team
    return None


def hydrate_access() -> None:
    """Populate access_store from Keycloak group membership for every namespace."""
    if not keycloak.enabled:
        logger.info("Keycloak admin disabled (no client secret); access table empty")
        return
    for ns in _all_namespaces():
        try:
            access_store[ns] = set(keycloak.group_members(ns))
        except KeycloakAdminError as e:
            logger.error("Could not hydrate access for %s: %s", ns, e)


@app.on_event("startup")
def _startup() -> None:
    hydrate_access()

# Pydantic models
class TeamCreate(BaseModel):
    name: str

class Team(BaseModel):
    id: str
    name: str
    created_at: datetime
    namespaces: List[str] = []

class NamespaceOrder(BaseModel):
    label: str                       # short suffix -> team-<name>-<label>

class UserRef(BaseModel):
    username: str
    firstName: str = ""
    lastName: str = ""
    email: str = ""
    roles: List[str] = []            # app realm roles (admin/team-leader/viewer)

class AccessGrant(BaseModel):
    namespace: str
    username: str

class NamespaceAccess(BaseModel):
    namespace: str
    team_id: str
    team_name: str
    users: List[str] = []

class PolicyResult(BaseModel):
    name: str
    kind: str
    enforcement_action: str
    compliant: bool
    violation_count: int
    messages: List[str]

class ComplianceSummary(BaseModel):
    team_id: str
    team_name: str
    namespace: Optional[str] = None
    namespaces: List[str] = []
    status: str                      # compliant | non_compliant | unknown
    reason: Optional[str] = None
    failing_policies: int
    total_policies: int
    checked_at: str

class ComplianceDetail(ComplianceSummary):
    policies: List[PolicyResult] = []

class RolloutStatus(BaseModel):
    strategy: str                    # BlueGreen | Canary | Unknown
    phase: str                       # Healthy | Paused | Progressing | Degraded ...
    message: str = ""
    active_version: Optional[str] = None
    preview_version: Optional[str] = None
    awaiting_promotion: bool = False

class AppPolicyResult(BaseModel):
    id: str
    name: str
    category: str                    # supply-chain | gatekeeper
    compliant: bool
    detail: str = ""
    kind: Optional[str] = None       # gatekeeper constraint kind
    enforcement_action: Optional[str] = None
    messages: List[str] = []

class AppCompliance(BaseModel):
    status: str                      # compliant | non_compliant | unknown
    reason: Optional[str] = None
    total_policies: int
    failing_policies: int
    policies: List[AppPolicyResult] = []

class Application(BaseModel):
    name: str
    namespace: Optional[str] = None  # which team namespace this app runs in
    version: str
    kind: str                        # Rollout | Deployment
    image: str
    replicas: int
    ready_replicas: int
    part_of: Optional[str] = None    # app.kubernetes.io/part-of (grouping key)
    component: Optional[str] = None  # app.kubernetes.io/component (web | api)
    url: Optional[str] = None        # browser URL: web -> page, api -> docs
    compliance: Optional[AppCompliance] = None
    rollout: Optional[RolloutStatus] = None

class TeamApplications(BaseModel):
    team_id: str
    team_name: str
    namespace: Optional[str] = None      # kept for back-compat (single-ns teams)
    namespaces: List[str] = []
    applications: List[Application] = []

# --- Namespace-scoped visibility -------------------------------------------
# Visibility is per-namespace: each team namespace is a Keycloak group, and the
# caller's token `groups` claim (namespace_scope) is the set of namespaces they
# may see. A team is visible if the caller can see ANY of its namespaces. The
# `admin` role (namespace_scope() -> None) sees everything.

def _visible_namespaces(request: Request, team: dict, scope: Optional[Set[str]]) -> List[str]:
    """The namespaces of `team` the caller is allowed to see:

    - admin / auth disabled (scope is None): ALL namespaces.
    - a **team-leader** with a foothold in the team (their groups intersect the
      team's namespaces): ALL of the team's namespaces — a lead manages the whole
      team, including namespaces they haven't been personally added to.
    - otherwise (a **viewer**): only the namespaces explicitly granted to them
      (the intersection of their groups with the team's namespaces).
    """
    nss = team.get("namespaces") or []
    if scope is None:
        return list(nss)
    granted = [ns for ns in nss if ns in scope]
    if granted and is_team_leader(request):
        return list(nss)
    return granted

def _scoped_teams(request: Request) -> List[dict]:
    """The teams the caller may see, each narrowed to their visible namespaces."""
    scope = namespace_scope(request)
    out = []
    for team in teams_store.values():
        visible = _visible_namespaces(request, team, scope)
        if scope is None or visible:
            out.append({**team, "namespaces": visible})
    return out

def _require_visible(request: Request, team_id: str) -> dict:
    """Return the team (narrowed to visible namespaces) iff it exists AND the
    caller can see at least one of its namespaces, else 404 (not 403) so
    out-of-scope teams don't leak their existence."""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")
    team = teams_store[team_id]
    scope = namespace_scope(request)
    visible = _visible_namespaces(request, team, scope)
    if scope is not None and not visible:
        raise HTTPException(status_code=404, detail="Team not found")
    return {**team, "namespaces": visible}

# --- Access management (order namespaces + grant/revoke user visibility) -----
# A caller "owns" a team if they can see any of its namespaces (admins own all).
# Owning a team lets them manage ALL of its namespaces — including ones just
# ordered that aren't in their own token yet.

def _owned_teams(request: Request) -> List[dict]:
    """Full team records (unmodified namespaces) the caller owns / may manage."""
    scope = namespace_scope(request)
    if scope is None:
        return list(teams_store.values())
    return [t for t in teams_store.values() if set(t.get("namespaces") or []) & scope]

def _owned_by_caller(request: Request, team_id: str) -> bool:
    """True if the caller owns/manages the given team."""
    return team_id in {t["id"] for t in _owned_teams(request)}

def _can_manage_namespace(request: Request, namespace: str) -> bool:
    """True if the caller owns the team that this namespace belongs to."""
    team = _team_for_namespace(namespace)
    return team is not None and _owned_by_caller(request, team["id"])

@app.get("/")
async def root():
    return {"message": "Teams API is running"}

@app.post("/teams", response_model=Team, dependencies=[Depends(require_admin)])
async def create_team(team: TeamCreate):
    """Create a new team (requires the admin role). The team gets a default
    namespace `team-<name>` and a matching Keycloak group for access grants."""
    # Check if team name already exists
    for existing_team in teams_store.values():
        if existing_team["name"].lower() == team.name.lower():
            raise HTTPException(status_code=400, detail="Team name already exists")

    # Generate unique ID and create team. created_at is stored as an ISO string
    # so the record round-trips cleanly through JSON persistence.
    team_id = str(uuid.uuid4())
    ns = default_namespace(team.name)
    new_team = {
        "id": team_id,
        "name": team.name,
        "created_at": datetime.now().isoformat(),
        "namespaces": [ns],
    }

    teams_store[team_id] = new_team
    save_teams()

    # Ensure the Keycloak group exists so users can be granted the namespace.
    # Best-effort: a Keycloak blip must not fail team creation (the operator will
    # still create the namespace; the group can be reconciled on next grant).
    if keycloak.enabled:
        try:
            keycloak.ensure_group(ns)
            access_store.setdefault(ns, set())
        except KeycloakAdminError as e:
            logger.error("Could not create Keycloak group for %s: %s", ns, e)

    return Team(**new_team)

@app.get("/teams", response_model=List[Team])
async def get_teams(request: Request):
    """Get the teams visible to the caller (scoped by their namespace grants)."""
    return [Team(**team) for team in _scoped_teams(request)]

@app.get("/teams/{team_id}", response_model=Team)
async def get_team(request: Request, team_id: str):
    """Get a specific team by ID (must be in the caller's scope)."""
    return Team(**_require_visible(request, team_id))

@app.delete("/teams/{team_id}", dependencies=[Depends(require_admin)])
async def delete_team(request: Request, team_id: str):
    """Delete a team and prune its namespaces (admin only)."""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")
    deleted_team = teams_store.pop(team_id)
    for ns in deleted_team.get("namespaces") or []:
        access_store.pop(ns, None)
    save_teams()
    return {"message": f"Team '{deleted_team['name']}' deleted successfully"}


@app.post(
    "/teams/{team_id}/namespaces",
    response_model=Team,
    dependencies=[Depends(require_manage)],
)
async def order_namespace(request: Request, team_id: str, order: NamespaceOrder):
    """Order an extra namespace for a team (team-leader for owned teams, or admin).

    Named `team-<name>-<label>`, added to the team's namespace list (the operator
    provisions it on its next poll), with a matching Keycloak group. The caller is
    auto-granted the new namespace so they keep managing it."""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")
    if not (_owned_by_caller(request, team_id)):
        raise HTTPException(status_code=404, detail="Team not found")
    if not _sanitize(order.label):
        raise HTTPException(status_code=400, detail="Invalid namespace label")

    team = teams_store[team_id]
    ns = ordered_namespace(team["name"], order.label)
    if ns in team["namespaces"]:
        raise HTTPException(status_code=400, detail="Namespace already exists")

    team["namespaces"].append(ns)
    save_teams()

    caller = getattr(request.state, "username", None)
    if keycloak.enabled:
        try:
            keycloak.ensure_group(ns)
            access_store.setdefault(ns, set())
            # Auto-grant the ordering user so the new namespace is theirs to manage.
            if caller:
                keycloak.add_user_to_group(caller, ns)
                access_store[ns].add(caller)
        except KeycloakAdminError as e:
            logger.error("Keycloak provisioning for %s failed: %s", ns, e)

    return Team(**team)

@app.get("/compliance", response_model=List[ComplianceSummary])
def get_all_compliance(request: Request):
    """Compliance summary (badge data) for the caller's visible teams."""
    return compliance_checker.summarize_all(_scoped_teams(request))

@app.get("/teams/{team_id}/compliance", response_model=ComplianceDetail)
def get_team_compliance(request: Request, team_id: str):
    """Detailed per-policy compliance breakdown for a single team (in scope)."""
    return compliance_checker.evaluate_team(_require_visible(request, team_id))

def _attach_compliance(team_apps: dict) -> dict:
    """Attach per-app compliance (supply-chain + Gatekeeper) to each app, using
    each app's own namespace (a team's apps may span several namespaces)."""
    for app in team_apps.get("applications", []):
        app["compliance"] = app_compliance_reader.compliance_for(
            app, app.get("namespace")
        )
    return team_apps

@app.get("/applications", response_model=List[TeamApplications])
def get_all_applications(request: Request):
    """Applications (name + version + compliance) in the caller's namespaces."""
    return [
        _attach_compliance(ta)
        for ta in applications_reader.applications_for_all(_scoped_teams(request))
    ]

@app.get("/teams/{team_id}/applications", response_model=TeamApplications)
def get_team_applications(request: Request, team_id: str):
    """Applications running in a single team's namespaces (in scope)."""
    team = _require_visible(request, team_id)
    return _attach_compliance(applications_reader.applications_for_team(team))

# --- Users + access management ----------------------------------------------

@app.get("/users", response_model=List[UserRef], dependencies=[Depends(require_manage)])
def list_users():
    """All Keycloak realm users — the pool leads/admins pick from to grant access."""
    if not keycloak.enabled:
        return []
    try:
        return keycloak.list_users()
    except KeycloakAdminError as e:
        logger.error("list users failed: %s", e)
        raise HTTPException(status_code=503, detail="Keycloak unavailable")

@app.get(
    "/access",
    response_model=List[NamespaceAccess],
    dependencies=[Depends(require_manage)],
)
def list_access(request: Request):
    """Namespace -> users assignments, scoped to the teams the caller owns
    (admins see every team's namespaces)."""
    rows: List[dict] = []
    for team in _owned_teams(request):
        for ns in team.get("namespaces") or []:
            rows.append(
                {
                    "namespace": ns,
                    "team_id": team["id"],
                    "team_name": team["name"],
                    "users": sorted(access_store.get(ns, set())),
                }
            )
    return sorted(rows, key=lambda r: r["namespace"])

@app.post("/access", dependencies=[Depends(require_manage)])
def grant_access(request: Request, grant: AccessGrant):
    """Grant a user visibility of a namespace (adds them to its Keycloak group)."""
    if not _can_manage_namespace(request, grant.namespace):
        raise HTTPException(status_code=403, detail="Not allowed to manage this namespace")
    if not keycloak.enabled:
        raise HTTPException(status_code=503, detail="Keycloak admin not configured")
    try:
        keycloak.add_user_to_group(grant.username, grant.namespace)
    except KeycloakAdminError as e:
        logger.error("grant failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Keycloak error: {e}")
    access_store.setdefault(grant.namespace, set()).add(grant.username)
    return {"message": f"Granted {grant.username} access to {grant.namespace}"}

@app.delete("/access", dependencies=[Depends(require_manage)])
def revoke_access(request: Request, grant: AccessGrant):
    """Revoke a user's access to a namespace (removes them from its Keycloak group)."""
    if not _can_manage_namespace(request, grant.namespace):
        raise HTTPException(status_code=403, detail="Not allowed to manage this namespace")
    if not keycloak.enabled:
        raise HTTPException(status_code=503, detail="Keycloak admin not configured")
    try:
        keycloak.remove_user_from_group(grant.username, grant.namespace)
    except KeycloakAdminError as e:
        logger.error("revoke failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Keycloak error: {e}")
    access_store.get(grant.namespace, set()).discard(grant.username)
    return {"message": f"Revoked {grant.username} access to {grant.namespace}"}

@app.get("/internal/teams")
def internal_teams():
    """UNAUTHENTICATED internal endpoint for the teams-operator to reconcile
    namespaces. Returns only id/name/namespaces (never compliance/apps/access),
    unscoped (the operator provisions every team's namespaces). Intended for
    in-cluster control-plane use only — restrict via NetworkPolicy in production."""
    return [
        {"id": t["id"], "name": t["name"], "namespaces": t.get("namespaces") or []}
        for t in teams_store.values()
    ]

@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes"""
    return {"status": "healthy", "teams_count": len(teams_store)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
