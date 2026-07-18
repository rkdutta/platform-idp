from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from compliance import ComplianceChecker
from workloads import ApplicationsReader
from app_compliance import AppComplianceReader
from auth import authenticate, require_read, require_team_leader, namespace_scope, AUTH_ENABLED

logger = logging.getLogger("teams-api")

# Where the team store is persisted. Backed by a PersistentVolume in-cluster so
# team data survives pod restarts (an in-memory store was wiped on every roll,
# which then made the operator prune the team namespaces).
DATA_DIR = os.getenv("DATA_DIR", "/data")
DATA_FILE = Path(DATA_DIR) / "teams.json"


def load_teams() -> Dict[str, Dict]:
    """Load the persisted team store; empty if the file is missing/unreadable."""
    try:
        if DATA_FILE.exists():
            with DATA_FILE.open() as f:
                teams = json.load(f)
            return {team["id"]: team for team in teams}
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
    version="1.4.0",
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

# Pydantic models
class TeamCreate(BaseModel):
    name: str

class Team(BaseModel):
    id: str
    name: str
    created_at: datetime

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
    namespace: Optional[str] = None
    applications: List[Application] = []

# --- Namespace-scoped visibility -------------------------------------------
# A team lead only sees the teams whose namespace their token grants (Keycloak
# group == namespace). The `admin` role (namespace_scope() -> None) sees all.

def _namespaces_by_team_id() -> Dict[str, str]:
    """team_id -> namespace, via the operator's team-id label on namespaces."""
    try:
        return applications_reader._team_namespaces()
    except Exception as e:  # noqa: BLE001 - never 500 the request on a lookup blip
        logger.error(f"Could not resolve team namespaces: {e}")
        return {}

def _scoped_teams(request: Request) -> List[dict]:
    """The team records the caller is allowed to see."""
    scope = namespace_scope(request)
    teams = list(teams_store.values())
    if scope is None:                      # admin / auth disabled -> everything
        return teams
    ns = _namespaces_by_team_id()
    return [t for t in teams if ns.get(t["id"]) in scope]

def _require_visible(request: Request, team_id: str) -> dict:
    """Return the team iff it exists AND is in the caller's scope, else 404.
    404 (not 403) so out-of-scope teams don't leak their existence."""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")
    scope = namespace_scope(request)
    if scope is not None and _namespaces_by_team_id().get(team_id) not in scope:
        raise HTTPException(status_code=404, detail="Team not found")
    return teams_store[team_id]

@app.get("/")
async def root():
    return {"message": "Teams API is running"}

@app.post("/teams", response_model=Team, dependencies=[Depends(require_team_leader)])
async def create_team(team: TeamCreate):
    """Create a new team (requires the team-leader role)"""
    # Check if team name already exists
    for existing_team in teams_store.values():
        if existing_team["name"].lower() == team.name.lower():
            raise HTTPException(status_code=400, detail="Team name already exists")

    # Generate unique ID and create team. created_at is stored as an ISO string
    # so the record round-trips cleanly through JSON persistence.
    team_id = str(uuid.uuid4())
    new_team = {
        "id": team_id,
        "name": team.name,
        "created_at": datetime.now().isoformat()
    }

    teams_store[team_id] = new_team
    save_teams()
    return Team(**new_team)

@app.get("/teams", response_model=List[Team])
async def get_teams(request: Request):
    """Get the teams visible to the caller (scoped by their namespace grants)."""
    return [Team(**team) for team in _scoped_teams(request)]

@app.get("/teams/{team_id}", response_model=Team)
async def get_team(request: Request, team_id: str):
    """Get a specific team by ID (must be in the caller's scope)."""
    return Team(**_require_visible(request, team_id))

@app.delete("/teams/{team_id}", dependencies=[Depends(require_team_leader)])
async def delete_team(request: Request, team_id: str):
    """Delete a team (team-leader role, and only within the caller's scope)."""
    deleted_team = _require_visible(request, team_id)
    teams_store.pop(team_id)
    save_teams()
    return {"message": f"Team '{deleted_team['name']}' deleted successfully"}

@app.get("/compliance", response_model=List[ComplianceSummary])
def get_all_compliance(request: Request):
    """Compliance summary (badge data) for the caller's visible teams."""
    return compliance_checker.summarize_all(_scoped_teams(request))

@app.get("/teams/{team_id}/compliance", response_model=ComplianceDetail)
def get_team_compliance(request: Request, team_id: str):
    """Detailed per-policy compliance breakdown for a single team (in scope)."""
    return compliance_checker.evaluate_team(_require_visible(request, team_id))

def _attach_compliance(team_apps: dict) -> dict:
    """Attach per-app compliance (supply-chain + Gatekeeper) to each app."""
    namespace = team_apps.get("namespace")
    for app in team_apps.get("applications", []):
        app["compliance"] = app_compliance_reader.compliance_for(app, namespace)
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
    """Applications running in a single team's namespace (in scope)."""
    team = _require_visible(request, team_id)
    return _attach_compliance(applications_reader.applications_for_team(team))

@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes"""
    return {"status": "healthy", "teams_count": len(teams_store)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
