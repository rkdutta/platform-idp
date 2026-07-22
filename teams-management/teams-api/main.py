from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Set
import asyncio
import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import store
import authz
from compliance import ComplianceChecker
from workloads import ApplicationsReader
from app_compliance import AppComplianceReader
from auth import (
    authenticate,
    require_read,
    require_admin,
    is_admin,
    caller_id,
    caller_name,
    AUTH_ENABLED,
    OIDC_ISSUER,
)
from keycloak_admin import KeycloakAdmin, KeycloakAdminError

logger = logging.getLogger("teams-api")

# Teams, ownership and access grants live in SQLite on the PersistentVolume (see
# store.py). DATA_FILE is the pre-2.0 JSON store, kept only as the migration
# source and a backup — nothing writes to it any more.
DATA_DIR = os.getenv("DATA_DIR", "/data")
DATA_FILE = Path(DATA_DIR) / "teams.json"

# How the cluster is reached from a developer's own machine — baked into the
# kubeconfig GET /kubeconfig serves (see below). Both are set once at bootstrap
# from the Terraform-generated kubeconfig (`grep server: platform-base/kubeconfig`)
# and are NOT auto-detected: the API server's host port is dynamically assigned
# by Docker and can change across a cluster recreate, at which point these must
# be updated too — see bootstrap/README.md.
K8S_API_SERVER = os.getenv("K8S_API_SERVER", "")
K8S_API_CA_CERT = os.getenv("K8S_API_CA_CERT", "")

# The CA that validates Keycloak's TLS cert for `kubectl oidc-login` (see
# _KUBECONFIG_TEMPLATE) — the same `platform-tls` wildcard cert every ingress
# in this cluster uses, including teams-api's own, so it's sourced from the
# Secret already mounted for that (no new out-of-band step — see
# bootstrap/README.md's existing platform-tls section).
KEYCLOAK_CA_CERT = os.getenv("KEYCLOAK_CA_CERT", "")


def _sanitize(value: str) -> str:
    """Turn an arbitrary string into a DNS-1123-ish namespace segment.

    Mirrors teams-operator.sanitize_namespace_name so the API and the operator
    agree on the namespace name derived from a team name / order label.
    """
    seg = "".join(c if c.isalnum() else "-" for c in value.lower())
    seg = "-".join(filter(None, seg.split("-")))  # collapse consecutive hyphens
    return seg.strip("-")[:53].strip("-")


def default_namespace(team_name: str) -> str:
    """The namespace a team gets by default: team-<sanitized-name>-default.

    Re-truncates after _sanitize (which budgets for a bare "team-" prefix) so
    the added "-default" suffix still fits Kubernetes' 63-char namespace limit.
    """
    suffix = "-default"
    max_name_len = 63 - len("team-") - len(suffix)
    name = _sanitize(team_name)[:max_name_len].strip("-")
    return f"team-{name}{suffix}"


def ordered_namespace(team_name: str, label: str) -> str:
    """A self-service ordered namespace: team-<name>-<label>."""
    return f"team-{_sanitize(team_name)}-{_sanitize(label)}"


# Every route is guarded by `authenticate` (validates the Keycloak JWT) then
# `require_read` (must be a valid realm user); both exempt public paths (/,
# /health, docs). What a caller may actually see or change is resolved per-request
# from the database by authz.py — team ownership and per-namespace roles.
app = FastAPI(
    title="Teams API",
    description="Team, namespace and access management for the engineering platform",
    version="2.0.0",
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

# Compliance checker (reads Gatekeeper state from the Kubernetes API).
compliance_checker = ComplianceChecker()

# Applications reader (lists Rollouts/Deployments in each team's namespace).
# Promotion/rollout management is handled by the Argo Rollouts dashboard, so the
# portal is read-only here.
applications_reader = ApplicationsReader()

# Per-app compliance (supply-chain evidence + Gatekeeper), attached to each app.
app_compliance_reader = AppComplianceReader(compliance_checker)

# Keycloak Admin API client. The database is still the sole authority for
# *app-layer* authorization (who owns what, who's granted what — nothing about
# that changes here). It's also used for one more thing: mirroring a derived
# slice of that DB state into Keycloak group membership, so k8s RBAC — which
# has no way to ask the DB anything — can learn "who's a viewer/maintainer of
# this namespace" via the OIDC `groups` claim instead. See
# _sync_group_membership / _group_reconciliation_loop below. Keycloak groups
# are a synced *projection*, never a second place authorization decisions are
# made — the reconciliation loop always overwrites them back to what the DB
# says, so hand-editing group membership in Keycloak wouldn't stick.
keycloak = KeycloakAdmin()


def _lookup_user(identifier: str) -> Optional[dict]:
    """Find a realm user by id or username. Grants are keyed on the Keycloak `sub`,
    so callers may pass either and we resolve to the canonical record."""
    if not keycloak.enabled or not identifier:
        return None
    try:
        for u in keycloak.list_users():
            if u.get("id") == identifier or u.get("username") == identifier:
                return u
    except KeycloakAdminError as e:
        logger.error("user lookup failed: %s", e)
    return None


# --- k8s RBAC via Keycloak groups --------------------------------------------
# teams-operator binds two static, never-updated RoleBindings per namespace —
# `{namespace}-viewer` -> ClusterRole view, `{namespace}-maintainer` ->
# ClusterRole edit — to Group subjects of these exact names. Kubernetes'
# native RBAC has no idea what "viewer"/"maintainer" mean; that meaning is
# entirely this naming convention plus that fixed wiring. Keycloak group
# *membership* is the only thing that changes at grant/revoke time, never a
# k8s object.

def _k8s_group_name(namespace: str, role: str) -> str:
    return f"{namespace}-{role}"


def _sync_group_membership(namespace: str, role: str, username: str, add: bool) -> None:
    """Best-effort mirror of one namespace-role grant into the matching
    Keycloak group. Never raises: the DB write already committed is the real
    source of truth for this request, and _group_reconciliation_loop is the
    self-healing backstop for whatever a transient Keycloak failure here
    misses — the same tolerance teams-operator's own poll loop already has
    for a transient teams-api outage."""
    if not keycloak.enabled:
        return
    group = _k8s_group_name(namespace, role)
    try:
        if add:
            keycloak.add_user_to_group(username, group)
        else:
            keycloak.remove_user_from_group(username, group)
    except KeycloakAdminError as e:
        logger.error(
            "k8s RBAC group sync failed (%s %s %s %s): %s",
            "add" if add else "remove", username, "->" if add else "<-", group, e,
        )


def _delete_k8s_groups(namespace: str) -> None:
    """Best-effort cleanup of a namespace's two k8s RBAC groups once the
    namespace/team is gone — otherwise Keycloak accumulates orphaned groups
    forever. Never raises."""
    if not keycloak.enabled:
        return
    for role in store.ROLES:
        try:
            keycloak.delete_group(_k8s_group_name(namespace, role))
        except KeycloakAdminError as e:
            logger.error("Could not delete k8s RBAC group for %s/%s: %s", namespace, role, e)


GROUP_RECONCILE_INTERVAL = int(os.getenv("GROUP_RECONCILE_INTERVAL", "60"))


def _reconcile_k8s_groups_once() -> None:
    """One reconciliation pass: recompute desired k8s RBAC group membership
    straight from the DB — the same computation internal_access() does,
    called in-process here (no HTTP hop needed, this runs inside teams-api
    itself) — and correct any drift against live Keycloak group membership.
    Split out from _group_reconciliation_loop so a single cycle is directly
    callable/testable without dealing with the sleep loop around it."""
    if not keycloak.enabled:
        return
    try:
        desired = internal_access()["namespaces"]
        for ns, roles in desired.items():
            for role in store.ROLES:
                want = set(roles.get(role, []))
                try:
                    have = set(keycloak.group_members(_k8s_group_name(ns, role)))
                except KeycloakAdminError as e:
                    logger.error(
                        "Could not read k8s RBAC group members for %s/%s: %s", ns, role, e
                    )
                    continue
                for username in want - have:
                    _sync_group_membership(ns, role, username, add=True)
                for username in have - want:
                    _sync_group_membership(ns, role, username, add=False)
    except Exception as e:  # noqa: BLE001 - a bad cycle must not kill the loop
        logger.error("k8s RBAC group reconciliation cycle failed: %s", e)


async def _group_reconciliation_loop() -> None:
    """Runs _reconcile_k8s_groups_once forever, spaced GROUP_RECONCILE_INTERVAL
    apart — the self-healing backstop for the best-effort syncs above. One bad
    cycle (e.g. Keycloak transiently unreachable) just retries next interval.
    """
    while True:
        await asyncio.sleep(GROUP_RECONCILE_INTERVAL)
        _reconcile_k8s_groups_once()


@app.on_event("startup")
async def _startup() -> None:
    """Open the database and, on a first run, seed it from the pre-2.0 state.

    The migration derives ownership and grants from the Keycloak groups this
    release replaces, so nobody loses access across the cutover. It only runs when
    the database has no teams, making restarts safe.
    """
    store.connect()

    # Started unconditionally, before the (unrelated) migration below can
    # early-return: the reconciliation loop already tolerates Keycloak being
    # down at any given cycle (see _group_reconciliation_loop) by skipping
    # and retrying next interval — it must still get that chance even if
    # Keycloak also happened to be down at this exact startup instant.
    asyncio.create_task(_group_reconciliation_loop())

    users_by_name: Dict[str, dict] = {}
    leaders: Set[str] = set()
    if keycloak.enabled:
        try:
            users_by_name = {u["username"]: u for u in keycloak.list_users()}
            leaders = set(keycloak.role_members("team-leader"))
        except KeycloakAdminError as e:
            # ABORT rather than migrate blind. Grants and ownership are derived
            # from the Keycloak directory, so migrating without it would import
            # the teams with nobody attached — and because the migration only runs
            # on an empty database, that wrong state would be permanent. Leaving
            # the database empty is loud, harmless and retried on the next restart.
            logger.error(
                "Keycloak directory unavailable (%s) — SKIPPING migration so it can "
                "retry on the next start. The API will report no teams until then.", e
            )
            return

    summary = store.migrate_from_legacy_json(
        DATA_FILE,
        members_of=keycloak.group_members if keycloak.enabled else (lambda ns: []),
        users_by_name=users_by_name,
        leaders=leaders,
        default_namespace_of=default_namespace,
    )
    logger.info("Store migration: %s", summary)

# Pydantic models
class TeamCreate(BaseModel):
    name: str

class OwnerRef(BaseModel):
    user_id: str
    username: str = ""

class Team(BaseModel):
    id: str
    name: str
    created_at: datetime
    namespaces: List[str] = []
    owners: List[OwnerRef] = []
    default_namespace: Optional[str] = None

class NamespaceOrder(BaseModel):
    label: str                       # short suffix -> team-<name>-<label>

class UserRef(BaseModel):
    id: str = ""                     # Keycloak `sub` — what grants are keyed on
    username: str
    firstName: str = ""
    lastName: str = ""
    email: str = ""
    roles: List[str] = []            # realm roles (only `admin` still carries authority)

class OwnerAdd(BaseModel):
    user_id: str                     # Keycloak id or username; resolved server-side

class AccessGrant(BaseModel):
    namespace: str
    user_id: str                     # Keycloak id or username; resolved server-side
    role: str = "viewer"             # viewer | maintainer (ignored on revoke)

class AccessUser(BaseModel):
    user_id: str
    username: str = ""
    role: str
    via: str = "grant"                # "owner" (implicit, via team ownership) | "grant" (explicit)

class NamespaceAccess(BaseModel):
    namespace: str
    team_id: str
    team_name: str
    users: List[AccessUser] = []

class NamespaceRole(BaseModel):
    namespace: str
    role: str                        # viewer | maintainer

class Me(BaseModel):
    """The caller's effective permissions, resolved server-side.

    Authority lives in the database now, so the UI cannot infer it from token
    roles — it asks for it here.
    """
    user_id: str = ""
    username: str = ""
    is_admin: bool = False
    owned_team_ids: List[str] = []
    namespaces: List[NamespaceRole] = []

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

def _with_owners(team: dict) -> dict:
    """Attach the team's owners and default namespace for the API response."""
    return {
        **team,
        "owners": store.owners_of(team["id"]),
        "default_namespace": store.default_namespace_of(team["id"]),
    }

@app.get("/")
async def root():
    return {"message": "Teams API is running"}

@app.get("/me", response_model=Me)
def get_me(request: Request):
    """The caller's effective permissions.

    Ownership and per-namespace roles are database state, so the UI has no way to
    derive them from the token — this is the single endpoint it trusts for what to
    render. It also means a permission change shows up on the next call, with no
    re-login or token refresh.
    """
    uid = caller_id(request)
    admin = is_admin(request)
    owned = sorted(store.owned_team_ids(uid))

    roles: Dict[str, str] = {}
    if admin:
        for ns in store.all_namespaces():
            roles[ns] = "maintainer"
    else:
        for team_id in owned:
            for ns in store.namespaces_of(team_id):
                roles[ns] = "maintainer"
        for ns, role in store.grants_for_user(uid).items():
            roles.setdefault(ns, role)

    return Me(
        user_id=uid,
        username=caller_name(request),
        is_admin=admin,
        owned_team_ids=owned,
        namespaces=[
            NamespaceRole(namespace=ns, role=role) for ns, role in sorted(roles.items())
        ],
    )

# A single template shared by every caller: it carries no per-user secret, just
# the cluster's connection info plus a generic `exec:` credential plugin —
# `kubectl oidc-login` (the standard int128/kubelogin plugin: must be installed
# locally, e.g. `brew install int128/kubelogin/kubelogin`) doing its own PKCE
# Authorization Code flow directly against Keycloak's `teams-cli` client (a
# public, PKCE-only client — no secret needed). Identity resolution happens
# entirely on the caller's own machine at kubectl invocation time, so this is
# safe to serve to any authenticated user (same authority as GET /me: read
# access to your own effective permissions, nothing more).
#
# --listen-address must match one of teams-cli's registered redirect URIs
# (127.0.0.1:8400) — it also has a wildcard path registered there
# (http://127.0.0.1:8400/*) because kubelogin's local callback server doesn't
# use the /callback path teams-cli's own login flow does.
_KUBECONFIG_TEMPLATE = """\
apiVersion: v1
kind: Config
clusters:
  - name: teams
    cluster:
      server: {server}
      certificate-authority-data: {ca_data}
contexts:
  - name: teams
    context:
      cluster: teams
      user: oidc
current-context: teams
users:
  - name: oidc
    user:
      exec:
        apiVersion: client.authentication.k8s.io/v1
        command: kubectl
        args:
          - oidc-login
          - get-token
          - --oidc-issuer-url={issuer}
          - --oidc-client-id=teams-cli
          - --oidc-extra-scope=profile
          - --oidc-extra-scope=email
          - --listen-address=127.0.0.1:8400
          - --certificate-authority-data={keycloak_ca_data}
        interactiveMode: IfAvailable
"""


@app.get("/kubeconfig")
def get_kubeconfig():
    """A ready-to-use kubeconfig: cluster connection info + a `kubectl
    oidc-login` `exec:` stanza. See _KUBECONFIG_TEMPLATE.

    Requires K8S_API_SERVER/K8S_API_CA_CERT/KEYCLOAK_CA_CERT to be configured
    (see main.py's top-level constants and bootstrap/README.md) — without them
    there's nothing to serve, and every caller would otherwise get the same
    unusable file, so this fails loudly instead.
    """
    if not K8S_API_SERVER or not K8S_API_CA_CERT or not KEYCLOAK_CA_CERT:
        raise HTTPException(
            status_code=503,
            detail="Cluster connection info not configured "
            "(K8S_API_SERVER/K8S_API_CA_CERT/KEYCLOAK_CA_CERT)",
        )
    body = _KUBECONFIG_TEMPLATE.format(
        server=K8S_API_SERVER,
        ca_data=base64.b64encode(K8S_API_CA_CERT.encode()).decode(),
        issuer=OIDC_ISSUER,
        keycloak_ca_data=base64.b64encode(KEYCLOAK_CA_CERT.encode()).decode(),
    )
    return Response(
        content=body,
        media_type="application/yaml",
        headers={"Content-Disposition": "attachment; filename=teams-kubeconfig.yaml"},
    )


@app.post("/teams", response_model=Team, dependencies=[Depends(require_admin)])
async def create_team(request: Request, team: TeamCreate):
    """Create a new team with its default namespace `team-<name>` (admin only).

    Assign owners separately via POST /teams/{id}/owners — ownership is what lets
    somebody manage the team's namespaces and access.
    """
    if store.team_name_exists(team.name):
        raise HTTPException(status_code=400, detail="Team name already exists")

    team_id = str(uuid.uuid4())
    ns = default_namespace(team.name)
    created = store.create_team(
        team_id, team.name, ns, created_at=datetime.now().isoformat()
    )
    store.record(caller_name(request), "team.create", team.name, ns)
    return Team(**_with_owners(created))

@app.get("/teams", response_model=List[Team])
async def get_teams(request: Request):
    """The teams visible to the caller, each narrowed to their visible namespaces."""
    return [Team(**_with_owners(team)) for team in authz.scoped_teams(request)]

@app.get("/teams/{team_id}", response_model=Team)
async def get_team(request: Request, team_id: str):
    """A specific team (must be in the caller's scope)."""
    return Team(**_with_owners(authz.require_visible_team(request, team_id)))

@app.delete("/teams/{team_id}", dependencies=[Depends(require_admin)])
async def delete_team(request: Request, team_id: str):
    """Delete a team (admin only). Namespaces, owners and grants cascade away, and
    the operator prunes the Kubernetes namespaces on its next poll."""
    team = store.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    namespaces = team.get("namespaces") or []
    store.delete_team(team_id)
    store.record(caller_name(request), "team.delete", team["name"])
    for ns in namespaces:
        _delete_k8s_groups(ns)
    return {"message": f"Team '{team['name']}' deleted successfully"}


# --- Ownership (admin only) --------------------------------------------------

@app.get("/teams/{team_id}/owners", response_model=List[OwnerRef])
def get_owners(request: Request, team_id: str):
    """The team's owners (admin, or an owner of this team)."""
    team = authz.require_team_owner(request, team_id)
    return store.owners_of(team["id"])

@app.post(
    "/teams/{team_id}/owners",
    response_model=List[OwnerRef],
    dependencies=[Depends(require_admin)],
)
def add_owner(request: Request, team_id: str, body: OwnerAdd):
    """Make a user an owner of this team (admin only).

    The user must exist in Keycloak — ownership is meaningless for an identity
    that can never log in, and a typo would otherwise be stored silently.
    """
    team = store.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    user = _lookup_user(body.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="No such user in Keycloak")

    store.add_owner(team_id, user["id"], user["username"])
    store.record(caller_name(request), "owner.add", team["name"], user["username"])

    # Ownership confers maintainer on every namespace of the team (see
    # authz.namespace_role) — mirror that into each one's maintainer k8s
    # group now, not just whichever namespace happens to exist by the next
    # reconciliation cycle.
    for ns in store.namespaces_of(team_id):
        _sync_group_membership(ns, "maintainer", user["username"], add=True)

    return store.owners_of(team_id)

@app.delete(
    "/teams/{team_id}/owners/{user_id}",
    response_model=List[OwnerRef],
    dependencies=[Depends(require_admin)],
)
def remove_owner(request: Request, team_id: str, user_id: str):
    """Remove an owner from this team (admin only)."""
    team = store.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Resolve the username before the DB write removes the ownership row.
    username = next(
        (o["username"] for o in store.owners_of(team_id) if o["user_id"] == user_id), None
    )

    store.remove_owner(team_id, user_id)
    store.record(caller_name(request), "owner.remove", team["name"], user_id)

    if username:
        for ns in store.namespaces_of(team_id):
            # Don't pull them out of the maintainer group if an independent
            # explicit grant on this namespace still justifies it.
            if store.grant_role(ns, user_id) != "maintainer":
                _sync_group_membership(ns, "maintainer", username, add=False)

    return store.owners_of(team_id)


# --- Namespaces (admin or team owner) ----------------------------------------

@app.post("/teams/{team_id}/namespaces", response_model=Team)
async def order_namespace(request: Request, team_id: str, order: NamespaceOrder):
    """Order an extra namespace `team-<name>-<label>` for a team (admin or owner).

    The operator provisions the actual Kubernetes namespace on its next poll. No
    grant is needed for the caller: owning the team already confers maintainer on
    every one of its namespaces.
    """
    team = authz.require_team_owner(request, team_id)
    if not _sanitize(order.label):
        raise HTTPException(status_code=400, detail="Invalid namespace label")

    ns = ordered_namespace(team["name"], order.label)
    if store.namespace_exists(ns):
        raise HTTPException(status_code=400, detail="Namespace already exists")

    store.add_namespace(team_id, ns)
    store.record(caller_name(request), "namespace.create", ns, team["name"])

    # Every current owner is already maintainer here per the DB model — mirror
    # that into the new namespace's maintainer k8s group immediately.
    for o in store.owners_of(team_id):
        _sync_group_membership(ns, "maintainer", o["username"], add=True)

    return Team(**_with_owners(store.get_team(team_id)))


@app.delete("/teams/{team_id}/namespaces/{namespace}", response_model=Team)
async def delete_namespace(request: Request, team_id: str, namespace: str):
    """Delete a namespace from a team, including its default namespace (admin
    or owner).

    The operator deletes the Kubernetes namespace on its next poll and the
    namespace's grants cascade away. A team can end up with zero namespaces
    this way — that's fine, ownership (not namespace count) is what keeps the
    team itself visible to its owner (see authz.scoped_teams).
    """
    team = authz.require_team_owner(request, team_id)
    if namespace not in team["namespaces"]:
        raise HTTPException(status_code=404, detail="Namespace not found")

    store.remove_namespace(namespace)
    store.record(caller_name(request), "namespace.delete", namespace, team["name"])
    _delete_k8s_groups(namespace)
    return Team(**_with_owners(store.get_team(team_id)))

@app.get("/compliance", response_model=List[ComplianceSummary])
def get_all_compliance(request: Request):
    """Compliance summary (badge data) for the caller's visible teams."""
    return compliance_checker.summarize_all(authz.scoped_teams(request))

@app.get("/teams/{team_id}/compliance", response_model=ComplianceDetail)
def get_team_compliance(request: Request, team_id: str):
    """Detailed per-policy compliance breakdown for a single team (in scope)."""
    return compliance_checker.evaluate_team(authz.require_visible_team(request, team_id))

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
        for ta in applications_reader.applications_for_all(authz.scoped_teams(request))
    ]

@app.get("/teams/{team_id}/applications", response_model=TeamApplications)
def get_team_applications(request: Request, team_id: str):
    """Applications running in a single team's namespaces (in scope)."""
    team = authz.require_visible_team(request, team_id)
    return _attach_compliance(applications_reader.applications_for_team(team))

# --- Users + access management ----------------------------------------------
# Keycloak is consulted only as the user DIRECTORY here. The grants themselves are
# written to the database, which is what makes them effective immediately.

@app.get("/users", response_model=List[UserRef])
def list_users(request: Request):
    """All Keycloak realm users — the pool owners/admins pick from when granting."""
    authz.require_any_owner(request)
    if not keycloak.enabled:
        return []
    try:
        users = keycloak.list_users()
    except KeycloakAdminError as e:
        logger.error("list users failed: %s", e)
        raise HTTPException(status_code=503, detail="Keycloak unavailable")
    # Opportunistically re-sync the denormalised usernames; ids are authoritative,
    # so a rename in Keycloak would otherwise leave stale display names behind.
    store.refresh_usernames({u["id"]: u["username"] for u in users if u.get("id")})
    return users

@app.get("/access", response_model=List[NamespaceAccess])
def list_access(request: Request):
    """Namespace -> users assignments, scoped to the teams the caller owns
    (admins see every namespace).

    A namespace's users are its explicit per-namespace grants PLUS its team's
    owners — ownership confers implicit `maintainer` on every namespace of the
    owned team (see authz.namespace_role) and isn't stored as a grant row, so it
    must be merged in here or an owner with no separate grant would show up with
    zero namespaces (they have full access via ownership, just never an explicit
    grant). An owner who also somehow holds an explicit grant is deduplicated in
    favor of the owner entry, since ownership is authoritative.
    """
    authz.require_any_owner(request)
    admin = is_admin(request)
    owned = store.owned_team_ids(caller_id(request))

    rows: List[dict] = []
    for team in store.list_teams():
        if not admin and team["id"] not in owned:
            continue
        owners = [
            {
                "user_id": o["user_id"],
                "username": o["username"],
                "role": "maintainer",
                "via": "owner",
            }
            for o in store.owners_of(team["id"])
        ]
        owner_ids = {o["user_id"] for o in owners}
        for ns in team["namespaces"]:
            grants = [
                {**g, "via": "grant"}
                for g in store.grants_for_namespace(ns)
                if g["user_id"] not in owner_ids
            ]
            rows.append(
                {
                    "namespace": ns,
                    "team_id": team["id"],
                    "team_name": team["name"],
                    "users": owners + grants,
                }
            )
    return sorted(rows, key=lambda r: r["namespace"])

@app.post("/access")
def grant_access(request: Request, grant: AccessGrant):
    """Grant a user a role in a namespace, or change the role they already hold.

    An upsert, so the UI has one code path for "add user" and "change role".
    """
    authz.require_namespace_manager(request, grant.namespace)
    if grant.role not in store.ROLES:
        raise HTTPException(
            status_code=400, detail=f"role must be one of {', '.join(store.ROLES)}"
        )
    user = _lookup_user(grant.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="No such user in Keycloak")

    old_role = store.grant_role(grant.namespace, user["id"])
    store.set_grant(grant.namespace, user["id"], user["username"], grant.role)
    store.record(
        caller_name(request), "access.grant", grant.namespace,
        f"{user['username']} as {grant.role}",
    )

    # Ownership already gives maintainer here via k8s group membership (see
    # add_owner) and always wins over an explicit grant (see internal_access's
    # dedup) — an explicit grant on an owner only changes the DB row, no
    # separate k8s-group effect.
    team = store.team_for_namespace(grant.namespace)
    if not (team and store.is_owner(user["id"], team["id"])):
        if old_role and old_role != grant.role:
            _sync_group_membership(grant.namespace, old_role, user["username"], add=False)
        _sync_group_membership(grant.namespace, grant.role, user["username"], add=True)

    return {
        "message": f"Granted {user['username']} {grant.role} on {grant.namespace}"
    }

@app.delete("/access")
def revoke_access(request: Request, grant: AccessGrant):
    """Revoke a user's role in a namespace. Effective on their next token
    refresh (see _sync_group_membership — the Keycloak group is what k8s RBAC
    actually reads, not a live per-request check anymore)."""
    authz.require_namespace_manager(request, grant.namespace)
    # Accept an id or a username, but never fail a revoke just because the
    # directory is unreachable — removing access must always be possible.
    user = _lookup_user(grant.user_id)
    user_id = user["id"] if user else grant.user_id
    old_role = store.grant_role(grant.namespace, user_id)
    store.remove_grant(grant.namespace, user_id)
    store.record(caller_name(request), "access.revoke", grant.namespace, user_id)

    if user and old_role:
        team = store.team_for_namespace(grant.namespace)
        if not (team and store.is_owner(user_id, team["id"])):
            _sync_group_membership(grant.namespace, old_role, user["username"], add=False)

    return {"message": f"Revoked access to {grant.namespace}"}

@app.get("/internal/teams")
def internal_teams():
    """UNAUTHENTICATED internal endpoint for the teams-operator to reconcile
    namespaces. Returns only id/name/namespaces (never compliance/apps/access),
    unscoped (the operator provisions every team's namespaces). Intended for
    in-cluster control-plane use only — restrict via NetworkPolicy in production."""
    return [
        {"id": t["id"], "name": t["name"], "namespaces": t["namespaces"]}
        for t in store.list_teams()
    ]


@app.get("/internal/access")
def internal_access():
    """UNAUTHENTICATED internal endpoint for teams-operator to sync namespace
    RBAC (Role/RoleBindings) to match teams-api's permission model:
    `{"namespaces": {ns: {"viewer": [username,...], "maintainer": [...]}},
    "admins": [username,...] | null}`.

    More sensitive than /internal/teams (who has access, not just namespace
    names exist) — same "restrict via NetworkPolicy in production" caveat as
    that endpoint, not yet enforced here.

    `admins` is null (never []) when the Keycloak directory is unreachable, so
    teams-operator knows to leave its cluster-admin ClusterRoleBinding
    untouched for that cycle rather than reconcile it to empty and revoke real
    admins over a transient outage.
    """
    namespaces: Dict[str, Dict[str, List[str]]] = {}
    for team in store.list_teams():
        owners = store.owners_of(team["id"])
        owner_ids = {o["user_id"] for o in owners}
        for ns in team["namespaces"]:
            viewer = []
            maintainer = [o["username"] for o in owners]
            for g in store.grants_for_namespace(ns):
                if g["user_id"] in owner_ids:
                    continue  # ownership already grants maintainer here
                (viewer if g["role"] == "viewer" else maintainer).append(g["username"])
            namespaces[ns] = {"viewer": viewer, "maintainer": maintainer}

    admins: Optional[List[str]] = None
    if keycloak.enabled:
        try:
            admins = keycloak.role_members("admin")
        except KeycloakAdminError as e:
            logger.error("Could not list admin role members: %s", e)

    return {"namespaces": namespaces, "admins": admins}


@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes"""
    return {"status": "healthy", "teams_count": len(store.list_teams())}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
