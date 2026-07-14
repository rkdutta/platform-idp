from fastapi import FastAPI, HTTPException
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
from rollouts import RolloutActions, ActionError

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

app = FastAPI(
    title="Teams API",
    description="A simple API for team leads to create and manage teams",
    version="1.0.0"
)

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
applications_reader = ApplicationsReader()

# Rollout actions (promote / set-image) via the argo-rollouts plugin.
rollout_actions = RolloutActions()

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

class Application(BaseModel):
    name: str
    version: str
    kind: str                        # Rollout | Deployment
    image: str
    replicas: int
    ready_replicas: int
    rollout: Optional[RolloutStatus] = None

class SetImageRequest(BaseModel):
    tag: str

class TeamApplications(BaseModel):
    team_id: str
    team_name: str
    namespace: Optional[str] = None
    applications: List[Application] = []

@app.get("/")
async def root():
    return {"message": "Teams API is running"}

@app.post("/teams", response_model=Team)
async def create_team(team: TeamCreate):
    """Create a new team"""
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
async def get_teams():
    """Get all teams"""
    return [Team(**team) for team in teams_store.values()]

@app.get("/teams/{team_id}", response_model=Team)
async def get_team(team_id: str):
    """Get a specific team by ID"""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")

    return Team(**teams_store[team_id])

@app.delete("/teams/{team_id}")
async def delete_team(team_id: str):
    """Delete a team"""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")

    deleted_team = teams_store.pop(team_id)
    save_teams()
    return {"message": f"Team '{deleted_team['name']}' deleted successfully"}

@app.get("/compliance", response_model=List[ComplianceSummary])
def get_all_compliance():
    """Compliance summary (badge data) for every team, from one cluster scan."""
    return compliance_checker.summarize_all(list(teams_store.values()))

@app.get("/teams/{team_id}/compliance", response_model=ComplianceDetail)
def get_team_compliance(team_id: str):
    """Detailed per-policy compliance breakdown for a single team."""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")

    return compliance_checker.evaluate_team(teams_store[team_id])

@app.get("/applications", response_model=List[TeamApplications])
def get_all_applications():
    """Applications (name + version) running in every team's namespace."""
    return applications_reader.applications_for_all(list(teams_store.values()))

@app.get("/teams/{team_id}/applications", response_model=TeamApplications)
def get_team_applications(team_id: str):
    """Applications running in a single team's namespace."""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")

    return applications_reader.applications_for_team(teams_store[team_id])

@app.post("/teams/{team_id}/apps/{app_name}/promote")
def promote_app(team_id: str, app_name: str):
    """Promote a blue/green rollout's preview (green) version to active (blue)."""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")
    try:
        return rollout_actions.promote(teams_store[team_id], app_name)
    except ActionError as e:
        raise HTTPException(status_code=e.status, detail=str(e))

@app.post("/teams/{team_id}/apps/{app_name}/image")
def set_app_image(team_id: str, app_name: str, req: SetImageRequest):
    """Deploy a new version of a rollout by changing its image tag (starts a green)."""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")
    try:
        return rollout_actions.set_image(teams_store[team_id], app_name, req.tag)
    except ActionError as e:
        raise HTTPException(status_code=e.status, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes"""
    return {"status": "healthy", "teams_count": len(teams_store)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
