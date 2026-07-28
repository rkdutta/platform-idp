#!/usr/bin/env python3
"""
Teams Operator - Creates Kubernetes namespaces when teams are created in the Teams API
"""

import asyncio
import glob
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Set, Dict, Any, Optional
import aiohttp
import requests
import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('teams-operator')

class TeamsOperator:
    def __init__(self):
        self.teams_api_url = os.getenv('TEAMS_API_URL', 'http://teams-api-service:80')
        self.poll_interval = int(os.getenv('POLL_INTERVAL', '30'))  # seconds
        # team_id -> the set of namespaces we've provisioned for that team. A team
        # can own several namespaces (a default plus any it self-service ordered),
        # so this is a set, reconciled against the team's desired `namespaces` list.
        self.team_namespaces: Dict[str, Set[str]] = {}
        
        # Initialize Kubernetes client
        try:
            # Try in-cluster config first (when running in pod)
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            # Fall back to local kubeconfig (for development)
            config.load_kube_config()
            logger.info("Loaded local kubeconfig")

        self.k8s_core_v1 = client.CoreV1Api()
        self.k8s_rbac_v1 = client.RbacAuthorizationV1Api()
        self.k8s_networking_v1 = client.NetworkingV1Api()

        # Cluster-wide RBAC subjects mirror teams-api's permission model onto real
        # k8s RoleBindings (per-namespace) + one ClusterRoleBinding (admins) — see
        # sync_namespace_rbac / sync_admin_binding.
        self.RBAC_MANAGED_BY = {"app.kubernetes.io/managed-by": "teams-operator"}
        self.VIEWER_BINDING = "teams-sync-viewer"
        self.MAINTAINER_BINDING = "teams-sync-maintainer"
        self.ADMIN_BINDING = "teams-admins"

        # Pre-built .dockerconfigjson for Harbor's private `platform` project,
        # sourced from this Deployment's own harbor-pull Secret (see
        # manifests/deployment.yaml) so the robot-account credential lives in
        # exactly one place. Empty means "not configured yet" (fresh bootstrap,
        # before the harbor-pull runbook step) - image-pull provisioning is
        # then skipped rather than crash-looping. See ensure_harbor_pull_secret.
        self.harbor_dockerconfigjson = os.getenv("HARBOR_DOCKERCONFIGJSON", "")
        self.HARBOR_PULL_SECRET = "harbor-pull"

        # Priority-scoped resource governance: three PriorityClasses
        # (tenant-critical/-standard/-besteffort — see
        # apps/resource/tenant-priority-classes) each get their own quota
        # bucket per tenant namespace, so a team's best-effort/batch work
        # can't eat into the capacity reserved for its must-run workloads.
        # A workload with no priorityClassName set gets defaulted to
        # tenant-standard by a Gatekeeper mutation (see
        # apps/security/tenant-guardrails's Assign objects), not here —
        # this only owns the quota objects themselves.
        #
        # The ResourceQuota manifests themselves are NOT hardcoded here —
        # they're templates mounted from a ConfigMap (see
        # apps/developer-control/teams-operator/manifests/quota-templates/
        # and this Deployment's quota-templates volume), rendered per
        # namespace in ensure_priority_quotas. Tuning a limit is then a
        # platform-infra-only change (edit the template, Argo syncs the
        # ConfigMap, the volume updates in place) — no operator image
        # rebuild needed.
        self.QUOTA_TEMPLATES_DIR = os.getenv("QUOTA_TEMPLATES_DIR", "/app/quota-templates")

        # Default per-container request/limit backstop for every tenant
        # namespace — same ConfigMap-mounted-template approach as the quotas
        # above (see apps/developer-control/teams-operator/manifests/
        # limitrange-templates/ and this Deployment's limitrange-templates
        # volume), rendered per namespace in ensure_limit_ranges.
        self.LIMITRANGE_TEMPLATES_DIR = os.getenv("LIMITRANGE_TEMPLATES_DIR", "/app/limitrange-templates")

        # Default network isolation for every tenant namespace (deny all
        # ingress, explicitly allow all egress) — same ConfigMap-mounted-
        # template approach as the quotas/limits above (see
        # apps/developer-control/teams-operator/manifests/
        # networkpolicy-templates/ and this Deployment's
        # networkpolicy-templates volume), rendered per namespace in
        # ensure_network_policies.
        self.NETWORKPOLICY_TEMPLATES_DIR = os.getenv("NETWORKPOLICY_TEMPLATES_DIR", "/app/networkpolicy-templates")

        # SPIFFE-authenticated OpenBao access: every project-* pod gets a JWT-SVID
        # + an openbao-agent sidecar (see apps/security/tenant-guardrails's
        # openbao-spiffe-volume-*.yaml / openbao-sidecar-*.yaml mutations) that
        # logs into a per-namespace JWT auth role scoped to that namespace's
        # slice of the kv KV mount. This operator creates that role (plus
        # its policy and the sidecars' agent-config ConfigMap) per namespace —
        # same ConfigMap-mounted-template approach as quotas/limits/netpols
        # above, except these templates aren't Kubernetes objects: the policy/
        # role templates become OpenBao HTTP API bodies (see
        # ensure_openbao_access), and the agentconfig templates become the
        # data keys of a per-namespace ConfigMap tenant pods mount directly.
        self.OPENBAO_POLICY_TEMPLATES_DIR = os.getenv("OPENBAO_POLICY_TEMPLATES_DIR", "/app/openbao-policy-templates")
        self.OPENBAO_ROLE_TEMPLATES_DIR = os.getenv("OPENBAO_ROLE_TEMPLATES_DIR", "/app/openbao-role-templates")
        self.OPENBAO_AGENTCONFIG_TEMPLATES_DIR = os.getenv("OPENBAO_AGENTCONFIG_TEMPLATES_DIR", "/app/openbao-agentconfig-templates")
        self.OPENBAO_AGENT_CONFIGMAP = "openbao-agent-config"

        # This operator's own access to OpenBao (to create the per-namespace
        # policies/roles above) uses the same SPIFFE trust chain as tenant
        # workloads, just with a more privileged role — see this Deployment's
        # own spiffe-helper sidecar (manifests/deployment.yaml) and the
        # one-time bootstrap in bootstrap/README.md. self._openbao_token /
        # self._openbao_token_expiry cache the client token from `bao write
        # auth/jwt/login`; _openbao_request() re-logs-in when it's stale or
        # missing rather than eagerly at startup, so a slow/late SVID doesn't
        # crash-loop the whole operator.
        self.openbao_addr = os.getenv("OPENBAO_ADDR", "http://openbao.openbao.svc.cluster.local:8200")
        self.openbao_jwt_path = os.getenv("OPENBAO_JWT_PATH", "/operator-shared/spiffe-jwt")
        self.openbao_role = os.getenv("OPENBAO_ROLE", "teams-operator-admin")
        self._openbao_token: Optional[str] = None
        self._openbao_token_expiry: float = 0.0
        # Cached accessor of the oidc/ auth mount, needed to bind identity
        # group-aliases (Vault/OpenBao keys aliases by mount *accessor*, not
        # mount path) — see _openbao_oidc_accessor / _ensure_openbao_group_alias.
        # Looked up once via sys/auth rather than hardcoded, since the
        # accessor is a random value assigned when `bao auth enable oidc`
        # runs (bootstrap/README.md) and would otherwise need updating here
        # by hand after every storage wipe.
        self._openbao_oidc_accessor_cache: Optional[str] = None

        # Per-namespace provisioning status (see update_namespace_status).
        # Deliberately a point-in-time "did the last reconcile attempt for
        # each concern succeed" snapshot, not continuous health monitoring
        # or drift detection, and never triggers any repair action on its
        # own — a team lead reads it (via teams-api/teams-app), it never
        # reads back or acts on itself. That was an explicit choice: a
        # system that actively polices/reverts a namespace's state would
        # fight normal day-to-day changes a developer makes inside their
        # own namespace.
        self.STATUS_ANNOTATION = "teams.example.com/provisioning-status"

        # Human-readable text for the Events update_namespace_status emits
        # on a condition transition (see _emit_event) — kept in sync with
        # teams-app's CONDITION_LABELS map (team-list.component.ts), which
        # renders the same condition types on the provisioning-status badge.
        self.CONDITION_LABELS = {
            "RBAC": "Team member access (view/edit permissions)",
            "ImagePullAccess": "Container image pulls (Harbor)",
            "ResourceQuota": "Resource quotas",
            "LimitRange": "Default resource limits",
            "NetworkPolicy": "Network isolation",
            "OpenBaoAccess": "Secrets access (OpenBao)",
        }

        # This operator's own namespace — the durable home for Events whose
        # involvedObject namespace is being (or has been) deleted, since an
        # Event stored *in* a namespace is cascade-deleted along with it and
        # would never reach the UI (see delete_namespace / _emit_event).
        # Set via the downward API in this Deployment's own manifest;
        # defaults to the one namespace this operator actually runs in.
        self.OPERATOR_NAMESPACE = os.getenv("OPERATOR_NAMESPACE", "engineering-platform")
        # Label every Event this operator emits with the owning team, so
        # teams-api can find them all with one cluster-wide label query
        # (list_event_for_all_namespaces) regardless of which namespace
        # actually stores them - see events_reader.py in teams-api.
        self.EVENT_TEAM_LABEL = "teams.example.com/team-id"

        # Last-synced admin subject set, so sync_admin_binding can emit an
        # Event only when the actual admin list changes - unlike the
        # per-namespace concerns, the ClusterRoleBinding here gets an
        # unconditional PATCH every reconcile cycle regardless of whether
        # anything changed, so without this an event would fire every ~30s.
        self._last_admin_usernames: Optional[Set[str]] = None

        # Authenticated identity for calling teams-api's /internal/* control-
        # plane endpoints (client-credentials grant, confidential client
        # teams-operator-sa - mirrors teams-api's own teams-api-sa client for
        # its Keycloak Admin API calls). Replaces the previous fully-open
        # /internal/* design - see teams-api's auth.require_operator.
        # KEYCLOAK_TOKEN_URL points at the same in-cluster Keycloak Service
        # teams-api itself uses (KeycloakAdmin.base in keycloak_admin.py).
        self.keycloak_token_url = os.getenv(
            "KEYCLOAK_TOKEN_URL",
            "http://keycloak-keycloakx-http.keycloak.svc/auth/realms/teams/protocol/openid-connect/token",
        )
        self.operator_client_id = os.getenv("OPERATOR_CLIENT_ID", "teams-operator-sa")
        self.operator_client_secret = os.getenv("OPERATOR_CLIENT_SECRET", "")
        self._api_token: Optional[str] = None
        self._api_token_expiry: float = 0.0

        # Argo CD self-service Project reconciliation (ensure_argocd_appproject
        # / ensure_argocd_rbac_policy below). Argo CD itself runs in
        # var.argocd_namespace (platform-base/argocd.tf) - "argocd" by
        # default, matching that Terraform variable's default.
        self.ARGOCD_NAMESPACE = os.getenv("ARGOCD_NAMESPACE", "argocd")
        self.ARGOCD_RBAC_CONFIGMAP = "argocd-rbac-cm"
        self.k8s_custom_objects = client.CustomObjectsApi()
        # Last-synced state per project (id -> (namespaces frozenset, source_repos
        # tuple)), so ensure_argocd_appproject/ensure_argocd_rbac_policy only
        # issue a write when something this operator manages actually changed -
        # same "don't patch every ~30s for no reason" motivation as
        # sync_admin_binding's _last_admin_usernames above.
        self._last_project_state: Dict[str, tuple] = {}
        # project_id -> argocd_project slug, tracked independently of
        # _last_project_state (populated even when unchanged/skipped) so that
        # once a project is deleted from teams-api - and its DB record is
        # gone by the time this operator's next poll notices - there's still
        # a way to know which AppProject/rbac policy block to clean up.
        self._project_slugs: Dict[str, str] = {}

    def _teams_api_token(self) -> Optional[str]:
        """Client-credentials token for calling teams-api's authenticated
        /internal/* endpoints as the teams-operator-sa confidential client
        (see teams-api's auth.require_operator). Cached until near expiry,
        same pattern as _openbao_login/_openbao_request. Returns None
        (logging the reason) if the client secret isn't configured yet or
        the token request fails — callers then treat it exactly like any
        other transient failure in this file (skip this cycle, retry next
        poll) rather than crash-looping."""
        if not self.operator_client_secret:
            logger.warning("⚠️ OPERATOR_CLIENT_SECRET not configured; /internal/* calls will be unauthenticated")
            return None
        if self._api_token and time.time() < self._api_token_expiry - 15:
            return self._api_token
        try:
            resp = requests.post(
                self.keycloak_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.operator_client_id,
                    "client_secret": self.operator_client_secret,
                },
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.error(f"❌ Keycloak token request failed (client_id={self.operator_client_id}): {e}")
            return None
        self._api_token = body["access_token"]
        self._api_token_expiry = time.time() + int(body.get("expires_in", 60))
        return self._api_token

    def _api_auth_headers(self) -> Dict[str, str]:
        token = self._teams_api_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def fetch_teams(self):
        """Fetch current teams (projects) from the Teams API, authenticated
        as teams-operator-sa (see _teams_api_token) — replaces the previous
        fully-open /internal/teams design. Returns just id/name/namespaces/
        source_repos/argocd_project for reconciliation.

        Returns the list of teams on success, or None if the API could not be
        reached / returned an error. None is deliberately distinct from an empty
        list: an empty list means "no teams exist" (prune namespaces), whereas
        None means "unknown" and reconciliation must be skipped — otherwise a
        transient API outage (e.g. during a teams-api rollout) would be read as
        "all teams deleted" and wipe every team namespace.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.teams_api_url}/internal/teams", headers=self._api_auth_headers()
                ) as response:
                    if response.status == 200:
                        teams = await response.json()
                        logger.debug(f"Fetched {len(teams)} teams from API")
                        return teams
                    else:
                        logger.error(f"Failed to fetch teams: HTTP {response.status}")
                        return None
        except aiohttp.ClientError as e:
            logger.error(f"Error connecting to Teams API: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching teams: {e}")
            return None

    async def fetch_access(self):
        """Fetch the current permission state from /internal/access,
        authenticated as teams-operator-sa (see _teams_api_token):
        `{"namespaces": {ns: {"viewer": [...], "maintainer": [...]}},
        "admins": [...] | None}`.

        Returns None (not the dict) if the API was unreachable/errored, same
        "skip this cycle" contract as fetch_teams — an RBAC sync built on a
        failed fetch would either leave stale access in place or, worse,
        reconcile every namespace's RoleBindings down to empty subjects.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.teams_api_url}/internal/access", headers=self._api_auth_headers()
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    logger.error(f"Failed to fetch access: HTTP {response.status}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Error connecting to Teams API for access: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching access: {e}")
            return None

    def ensure_argocd_appproject(self, argocd_project: str, namespaces: Set[str], source_repos: list) -> bool:
        """Ensure an Argo CD AppProject exists for this project, with
        `sourceRepos`/`destinations` reconciled to match teams-api's records
        (unlike the create-if-missing-only helpers elsewhere in this file,
        these two fields can legitimately change after creation — a project
        gaining a namespace or a source repo — so this really does patch on
        every change, not just create-once).

        `destinations` covers every namespace teams-api has provisioned for
        this project; `sourceRepos` starts empty (deny-by-default) until an
        admin/project-manager adds one via teams-api's source-repos
        endpoints. Deliberately does NOT set spec.roles — Argo CD RBAC here
        is centralized in argocd-rbac-cm's policy.csv (see
        ensure_argocd_rbac_policy), not the AppProject's own alternate,
        decentralized role mechanism.
        """
        spec = {
            "sourceRepos": list(source_repos),
            "destinations": [
                {"server": "https://kubernetes.default.svc", "namespace": ns}
                for ns in sorted(namespaces)
            ],
        }
        body = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "AppProject",
            "metadata": {
                "name": argocd_project,
                "namespace": self.ARGOCD_NAMESPACE,
                "labels": {"app.kubernetes.io/managed-by": "teams-operator"},
            },
            "spec": spec,
        }
        try:
            self.k8s_custom_objects.create_namespaced_custom_object(
                group="argoproj.io", version="v1alpha1", namespace=self.ARGOCD_NAMESPACE,
                plural="appprojects", body=body,
            )
            logger.info(f"✅ Created AppProject '{argocd_project}'")
            return True
        except ApiException as e:
            if e.status == 409:
                try:
                    self.k8s_custom_objects.patch_namespaced_custom_object(
                        group="argoproj.io", version="v1alpha1", namespace=self.ARGOCD_NAMESPACE,
                        plural="appprojects", name=argocd_project, body={"spec": spec},
                    )
                    return True
                except ApiException as patch_err:
                    logger.error(f"❌ Failed to update AppProject '{argocd_project}': {patch_err}")
                    return False
            logger.error(f"❌ Failed to create AppProject '{argocd_project}': {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error ensuring AppProject '{argocd_project}': {e}")
            return False

    def _rbac_policy_block(self, argocd_project: str, namespaces: Set[str]) -> str:
        """The delimited policy.csv block for one project's viewer/maintainer
        roles — see ensure_argocd_rbac_policy. Explicit resource types (not a
        `*` wildcard): most Argo CD RBAC resources (clusters/repositories/
        accounts/certificates/gpgkeys) are global, not project-scoped, so
        wildcarding the resource column would either do nothing useful or
        leak into applicationsets. `exec` deliberately excluded from both
        roles (shell access is a materially different grant than viewing/
        maintaining).

        The `g,` lines deliberately do NOT reference a dedicated
        `project-<name>-viewer`/`-maintainer` Keycloak group (an earlier
        version of this did, and needed its own ensure_keycloak_groups sync
        step) — they instead bind each of the project's *namespaces'*
        existing `{namespace}-viewer`/`-maintainer` k8s RBAC groups directly
        to the same Argo CD role. Those groups already exist and already
        have correct membership (teams-api's own _sync_group_membership /
        _reconcile_k8s_groups_once), so this reuses them instead of
        maintaining a second, parallel set of groups and a second sync
        mechanism for the same underlying access decision — one fewer place
        for Keycloak group sprawl and one fewer thing that can drift. A user
        who's viewer/maintainer of ANY namespace in the project gets that
        role on the whole Argo CD project, same as before (Casbin unions
        every role a subject holds via any matching `g,` line - no explicit
        aggregation needed here, unlike the old per-project-group approach
        which had to compute that union itself before syncing membership)."""
        p = argocd_project
        g_lines = "".join(
            f"g, {ns}-viewer, role:{p}-viewer\n"
            f"g, {ns}-maintainer, role:{p}-maintainer\n"
            for ns in sorted(namespaces)
        )
        return (
            f"# BEGIN project {p}\n"
            f"p, role:{p}-viewer, applications, get, {p}/*, allow\n"
            f"p, role:{p}-viewer, applicationsets, get, {p}/*, allow\n"
            f"p, role:{p}-viewer, logs, get, {p}/*, allow\n"
            f"p, role:{p}-viewer, projects, get, {p}, allow\n"
            f"p, role:{p}-maintainer, applications, *, {p}/*, allow\n"
            f"p, role:{p}-maintainer, applicationsets, *, {p}/*, allow\n"
            f"p, role:{p}-maintainer, logs, get, {p}/*, allow\n"
            f"p, role:{p}-maintainer, projects, get, {p}, allow\n"
            f"{g_lines}"
            f"# END project {p}\n"
        )

    def ensure_argocd_rbac_policy(self, argocd_project: str, namespaces: Set[str]) -> bool:
        """Add/update this project's delimited policy.csv block in
        argocd-rbac-cm (`# BEGIN project <name>` / `# END project <name>`),
        touching no other project's block and none of the Terraform-seeded
        baseline (see platform-base/argocd.tf's kubernetes_config_map.argocd_
        rbac and its `configs.rbac.create=false` handoff). Argo CD hot-
        reloads this ConfigMap via an informer watch, so this takes effect
        without a restart."""
        try:
            cm = self.k8s_core_v1.read_namespaced_config_map(self.ARGOCD_RBAC_CONFIGMAP, self.ARGOCD_NAMESPACE)
        except ApiException as e:
            logger.error(f"❌ Could not read '{self.ARGOCD_RBAC_CONFIGMAP}': {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error reading '{self.ARGOCD_RBAC_CONFIGMAP}': {e}")
            return False

        policy = (cm.data or {}).get("policy.csv", "")
        begin = f"# BEGIN project {argocd_project}"
        end = f"# END project {argocd_project}"
        new_block = self._rbac_policy_block(argocd_project, namespaces)

        if begin in policy and end in policy:
            pre = policy[: policy.index(begin)]
            post = policy[policy.index(end) + len(end):].lstrip("\n")
            updated = pre + new_block + post
        else:
            sep = "\n" if policy and not policy.endswith("\n") else ""
            updated = policy + sep + new_block

        if updated == policy:
            return True  # already up to date, no patch needed

        try:
            self.k8s_core_v1.patch_namespaced_config_map(
                self.ARGOCD_RBAC_CONFIGMAP, self.ARGOCD_NAMESPACE,
                {"data": {"policy.csv": updated}},
            )
            logger.info(f"✅ Ensured Argo CD RBAC policy block for project '{argocd_project}'")
            return True
        except ApiException as e:
            logger.error(f"❌ Failed to patch '{self.ARGOCD_RBAC_CONFIGMAP}' for project '{argocd_project}': {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error patching '{self.ARGOCD_RBAC_CONFIGMAP}' for project '{argocd_project}': {e}")
            return False

    def _remove_rbac_policy_block(self, argocd_project: str) -> bool:
        """Inverse of ensure_argocd_rbac_policy, for project deletion -
        strips exactly this project's delimited block, touching nothing
        else in policy.csv."""
        try:
            cm = self.k8s_core_v1.read_namespaced_config_map(self.ARGOCD_RBAC_CONFIGMAP, self.ARGOCD_NAMESPACE)
        except ApiException as e:
            if e.status == 404:
                return True
            logger.error(f"❌ Could not read '{self.ARGOCD_RBAC_CONFIGMAP}': {e}")
            return False

        policy = (cm.data or {}).get("policy.csv", "")
        begin = f"# BEGIN project {argocd_project}"
        end = f"# END project {argocd_project}"
        if begin not in policy or end not in policy:
            return True  # already gone

        pre = policy[: policy.index(begin)]
        post = policy[policy.index(end) + len(end):].lstrip("\n")
        updated = pre + post
        try:
            self.k8s_core_v1.patch_namespaced_config_map(
                self.ARGOCD_RBAC_CONFIGMAP, self.ARGOCD_NAMESPACE, {"data": {"policy.csv": updated}}
            )
            logger.info(f"🗑️ Removed Argo CD RBAC policy block for project '{argocd_project}'")
            return True
        except ApiException as e:
            logger.error(f"❌ Failed to remove RBAC policy block for '{argocd_project}': {e}")
            return False

    def delete_argocd_applications(self, argocd_project: str) -> bool:
        """Delete every Argo CD Application belonging to this project
        (spec.project == argocd_project) - project deletion.

        Deleting the AppProject does NOT cascade-delete the Applications
        that reference it (no k8s ownerReference relationship between them),
        so without this they'd be orphaned: left behind in the argocd
        namespace, referencing a project that no longer exists. Each delete
        goes through Argo CD's own resources-finalizer (if the Application
        has one), which prunes its live managed resources via Argo CD's own
        logic - independent of (and a harmless no-op race against) this same
        reconcile pass's namespace deletion, since a resource that's already
        gone is treated as successfully pruned. Called before
        delete_argocd_appproject, mirroring "detach applications, then
        delete the project" - Argo CD doesn't hard-block deleting an
        AppProject with live references, but there's no reason to race it.
        """
        try:
            apps = self.k8s_custom_objects.list_namespaced_custom_object(
                group="argoproj.io", version="v1alpha1", namespace=self.ARGOCD_NAMESPACE,
                plural="applications",
            )
        except ApiException as e:
            logger.error(f"❌ Could not list Applications to clean up for project '{argocd_project}': {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error listing Applications for project '{argocd_project}': {e}")
            return False

        ok = True
        for app in apps.get("items", []):
            if app.get("spec", {}).get("project") != argocd_project:
                continue
            name = app["metadata"]["name"]
            try:
                self.k8s_custom_objects.delete_namespaced_custom_object(
                    group="argoproj.io", version="v1alpha1", namespace=self.ARGOCD_NAMESPACE,
                    plural="applications", name=name,
                )
                logger.info(f"🗑️ Deleted Application '{name}' (project '{argocd_project}')")
            except ApiException as e:
                if e.status != 404:
                    logger.error(f"❌ Failed to delete Application '{name}' (project '{argocd_project}'): {e}")
                    ok = False
            except Exception as e:
                logger.error(f"❌ Unexpected error deleting Application '{name}' (project '{argocd_project}'): {e}")
                ok = False
        return ok

    def delete_argocd_appproject(self, argocd_project: str) -> bool:
        """Delete this project's AppProject CR (project deletion)."""
        try:
            self.k8s_custom_objects.delete_namespaced_custom_object(
                group="argoproj.io", version="v1alpha1", namespace=self.ARGOCD_NAMESPACE,
                plural="appprojects", name=argocd_project,
            )
            logger.info(f"🗑️ Deleted AppProject '{argocd_project}'")
            return True
        except ApiException as e:
            if e.status == 404:
                return True
            logger.error(f"❌ Failed to delete AppProject '{argocd_project}': {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error deleting AppProject '{argocd_project}': {e}")
            return False

    def _emit_project_event(self, team_id: str, reason: str, message: str, healthy: bool = True) -> None:
        """Emit an Event for a project-level (not namespace-level) reconcile
        action — Keycloak groups, the AppProject, or the argocd-rbac-cm
        policy block. Labelled with the project id (same EVENT_TEAM_LABEL as
        every other Event here) so it surfaces in the Teams portal's
        per-project activity feed (events_reader.py's cluster-wide label
        query) alongside this project's per-namespace events, even though
        there's no single owning namespace to attach it to. Stored in this
        operator's own namespace, same reasoning as _emit_cluster_event."""
        now = datetime.now(timezone.utc)
        body = client.CoreV1Event(
            metadata=client.V1ObjectMeta(
                generate_name=f"teams-operator-project-{team_id}-",
                labels={self.EVENT_TEAM_LABEL: team_id},
            ),
            involved_object=client.V1ObjectReference(
                kind="AppProject", name=team_id, namespace=self.ARGOCD_NAMESPACE,
                api_version="argoproj.io/v1alpha1",
            ),
            reason=reason,
            message=message,
            type="Normal" if healthy else "Warning",
            source=client.V1EventSource(component="teams-operator"),
            first_timestamp=now,
            last_timestamp=now,
            count=1,
        )
        try:
            self.k8s_core_v1.create_namespaced_event(self.OPERATOR_NAMESPACE, body)
        except ApiException as e:
            logger.error(f"❌ Failed to emit Event ({reason}) for project '{team_id}': {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error emitting Event ({reason}) for project '{team_id}': {e}")

    def sync_namespace_rbac(self, namespace: str) -> bool:
        """Ensure the two static RoleBindings exist that give k8s RBAC real
        effect in `namespace`, bound to Group subjects named deterministically
        from the namespace ("{namespace}-viewer" / "{namespace}-maintainer" —
        must match teams-api's _k8s_group_name). *Membership* in those groups
        (who's actually a viewer/maintainer right now) is synced straight into
        Keycloak by teams-api itself, not here — these bindings never change
        once created, so this is create-if-missing, no per-cycle patch.
        Returns whether both bindings are present/created OK this cycle —
        surfaced as the "RBAC" condition by update_namespace_status."""
        ok = True
        for binding_name, cluster_role, role_tier in (
            (self.VIEWER_BINDING, "view", "viewer"),
            (self.MAINTAINER_BINDING, "edit", "maintainer"),
        ):
            ok = self._ensure_group_role_binding(namespace, binding_name, cluster_role, role_tier) and ok
        return ok

    def _ensure_group_role_binding(
        self, namespace: str, name: str, cluster_role: str, role_tier: str
    ) -> bool:
        group_name = f"{namespace}-{role_tier}"
        body = client.V1RoleBinding(
            metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=self.RBAC_MANAGED_BY),
            role_ref=client.V1RoleRef(
                api_group="rbac.authorization.k8s.io", kind="ClusterRole", name=cluster_role
            ),
            subjects=[
                client.V1Subject(kind="Group", name=group_name, api_group="rbac.authorization.k8s.io")
            ],
        )
        try:
            self.k8s_rbac_v1.create_namespaced_role_binding(namespace, body)
            logger.info(f"✅ Created RoleBinding '{name}' in '{namespace}' (Group: {group_name})")
            return True
        except ApiException as e:
            if e.status == 409:
                return True  # already exists, subjects never change — nothing to reconcile
            logger.error(f"❌ Failed to create RoleBinding '{name}' in '{namespace}': {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error creating RoleBinding '{name}' in '{namespace}': {e}")
            return False

    def sync_admin_binding(self, usernames) -> None:
        """Reconcile the single cluster-wide ClusterRoleBinding that gives
        Keycloak `admin`-role holders real cluster-admin. Caller is
        responsible for not calling this when the admin list is unknown
        (None) — see reconcile_teams."""
        new_admins = set(usernames)
        changed = new_admins != self._last_admin_usernames
        subjects = [
            client.V1Subject(kind="User", name=u, api_group="rbac.authorization.k8s.io")
            for u in usernames
        ]
        body = client.V1ClusterRoleBinding(
            metadata=client.V1ObjectMeta(name=self.ADMIN_BINDING, labels=self.RBAC_MANAGED_BY),
            role_ref=client.V1RoleRef(
                api_group="rbac.authorization.k8s.io", kind="ClusterRole", name="cluster-admin"
            ),
            subjects=subjects,
        )
        try:
            self.k8s_rbac_v1.create_cluster_role_binding(body)
            logger.info(f"✅ Created ClusterRoleBinding '{self.ADMIN_BINDING}' ({len(subjects)} admin(s))")
            self._emit_cluster_event(self.ADMIN_BINDING, "AdminBindingSynced",
                                      f"cluster-admin granted to {len(subjects)} admin(s)")
            self._last_admin_usernames = new_admins
        except ApiException as e:
            if e.status == 409:
                try:
                    self.k8s_rbac_v1.patch_cluster_role_binding(
                        self.ADMIN_BINDING, {"subjects": [s.to_dict() for s in subjects]}
                    )
                    # Patched every cycle regardless of change (the API call
                    # itself doesn't distinguish a no-op patch) - only emit
                    # an Event when the admin set actually differs from last
                    # time, or this would fire every ~30s forever.
                    if changed:
                        self._emit_cluster_event(self.ADMIN_BINDING, "AdminBindingSynced",
                                                  f"cluster-admin now granted to {len(subjects)} admin(s)")
                        self._last_admin_usernames = new_admins
                except ApiException as patch_err:
                    logger.error(f"❌ Failed to update ClusterRoleBinding '{self.ADMIN_BINDING}': {patch_err}")
            else:
                logger.error(f"❌ Failed to create ClusterRoleBinding '{self.ADMIN_BINDING}': {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error syncing ClusterRoleBinding '{self.ADMIN_BINDING}': {e}")

    def ensure_harbor_pull_secret(self, namespace: str) -> bool:
        """Ensure `namespace` has the harbor-pull imagePullSecret, so
        workloads deployed there can pull from Harbor's private `platform`
        project — without this, every tenant workload 403s on image pull the
        same way engineering-platform's own components would without it.
        Create-if-missing only: like the RoleBindings, this is never patched
        again once it exists, so a manual credential rotation (new Secret
        content + operator redeploy) can't be silently overwritten by a
        stale in-memory value from a long-running pod. Returns False (not
        just skips) when harbor_dockerconfigjson isn't configured yet — that
        genuinely means image pulls will fail, worth surfacing as
        "ImagePullAccess" not-ready rather than hiding it as a silent skip."""
        if not self.harbor_dockerconfigjson:
            return False
        body = client.V1Secret(
            metadata=client.V1ObjectMeta(name=self.HARBOR_PULL_SECRET, namespace=namespace),
            type="kubernetes.io/dockerconfigjson",
            string_data={".dockerconfigjson": self.harbor_dockerconfigjson},
        )
        try:
            self.k8s_core_v1.create_namespaced_secret(namespace, body)
            logger.info(f"✅ Created imagePullSecret '{self.HARBOR_PULL_SECRET}' in '{namespace}'")
            return True
        except ApiException as e:
            if e.status == 409:
                return True  # already exists
            logger.error(f"❌ Failed to create imagePullSecret in '{namespace}': {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error creating imagePullSecret in '{namespace}': {e}")
            return False

    def ensure_default_sa_pull_secret(self, namespace: str) -> bool:
        """Attach harbor-pull to the namespace's default ServiceAccount, so
        every pod using it (the common case — app manifests owned by their
        own repos don't declare imagePullSecrets themselves) picks it up
        with no per-workload change needed."""
        if not self.harbor_dockerconfigjson:
            return False
        try:
            sa = self.k8s_core_v1.read_namespaced_service_account("default", namespace)
        except ApiException as e:
            if e.status != 404:
                logger.error(f"❌ Could not read default ServiceAccount in '{namespace}': {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error reading default ServiceAccount in '{namespace}': {e}")
            return False

        existing = sa.image_pull_secrets or []
        if any(ref.name == self.HARBOR_PULL_SECRET for ref in existing):
            return True  # already attached

        try:
            self.k8s_core_v1.patch_namespaced_service_account(
                "default",
                namespace,
                {"imagePullSecrets": [ref.to_dict() for ref in existing] + [{"name": self.HARBOR_PULL_SECRET}]},
            )
            logger.info(f"✅ Attached imagePullSecret '{self.HARBOR_PULL_SECRET}' to default SA in '{namespace}'")
            return True
        except ApiException as e:
            logger.error(f"❌ Failed to patch default ServiceAccount in '{namespace}': {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error patching default ServiceAccount in '{namespace}': {e}")
            return False

    def _apply_namespaced_templates(self, namespace: str, templates_dir: str, create_fn) -> bool:
        """Render every *.yaml template in `templates_dir` for `namespace`
        (substituting {{ NAMESPACE }}) and create-if-missing via `create_fn`
        (a bound create_namespaced_* method, from whichever Api client
        matches the template's kind). Shared by ensure_priority_quotas,
        ensure_limit_ranges and ensure_network_policies — same contract
        (never patched again once it exists, so a hand-tuned value in the
        cluster doesn't get silently reverted), different Kubernetes API
        call and directory.

        Templates are read fresh from disk on every call (never cached), so
        editing a ConfigMap-mounted template takes effect on this operator's
        very next reconciliation cycle, no restart required. Returns True
        only if every template applied (or already existed) cleanly — one
        failure among several templates still reports the whole concern as
        not-ready, since e.g. a namespace with 2 of 3 quota tiers missing is
        a real gap, not a detail to bury in a per-file log line."""
        template_paths = sorted(glob.glob(os.path.join(templates_dir, "*.yaml")))
        if not template_paths:
            logger.warning(f"No templates found in {templates_dir}; skipping")
            return False

        ok = True
        for path in template_paths:
            with open(path) as f:
                rendered = f.read().replace("{{ NAMESPACE }}", namespace)
            try:
                body = yaml.safe_load(rendered)
            except yaml.YAMLError as e:
                logger.error(f"❌ Template {path} is not valid YAML after rendering: {e}")
                ok = False
                continue
            kind = body.get("kind", "resource")
            name = body.get("metadata", {}).get("name", os.path.basename(path))
            try:
                create_fn(namespace, body)
                logger.info(f"✅ Created {kind} '{name}' in '{namespace}' (from {os.path.basename(path)})")
            except ApiException as e:
                if e.status != 409:  # 409 = already exists, fine
                    logger.error(f"❌ Failed to create {kind} '{name}' in '{namespace}': {e}")
                    ok = False
            except Exception as e:
                logger.error(f"❌ Unexpected error creating {kind} '{name}' in '{namespace}': {e}")
                ok = False
        return ok

    def ensure_priority_quotas(self, namespace: str) -> bool:
        """Ensure `namespace` has one PriorityClass-scoped ResourceQuota per
        tenant tier (tenant-critical/-standard/-besteffort), so best-effort
        workloads can never starve a team's must-run ones of quota. The
        manifests themselves live as templates on disk (QUOTA_TEMPLATES_DIR
        — see the class-level comment), not as Python objects."""
        return self._apply_namespaced_templates(
            namespace, self.QUOTA_TEMPLATES_DIR, self.k8s_core_v1.create_namespaced_resource_quota
        )

    def ensure_limit_ranges(self, namespace: str) -> bool:
        """Ensure `namespace` has the default tenant LimitRange, so a
        container that doesn't declare its own requests/limits gets a sane
        default instead of running unbounded or with nothing at all. Same
        template-on-disk approach as ensure_priority_quotas — see
        LIMITRANGE_TEMPLATES_DIR."""
        return self._apply_namespaced_templates(
            namespace, self.LIMITRANGE_TEMPLATES_DIR, self.k8s_core_v1.create_namespaced_limit_range
        )

    def ensure_network_policies(self, namespace: str) -> bool:
        """Ensure `namespace` has the default tenant NetworkPolicy (deny all
        ingress, explicitly allow all egress — see
        networkpolicy-templates/default.yaml for why egress needs an
        explicit rule rather than just being left ungoverned). Same
        template-on-disk approach as ensure_priority_quotas — see
        NETWORKPOLICY_TEMPLATES_DIR."""
        return self._apply_namespaced_templates(
            namespace, self.NETWORKPOLICY_TEMPLATES_DIR, self.k8s_networking_v1.create_namespaced_network_policy
        )

    def _openbao_login(self) -> Optional[str]:
        """Log in to OpenBao via its jwt auth method, using this pod's own
        JWT-SVID (written by the spiffe-helper sidecar — see
        manifests/deployment.yaml). Caches the client token until it's near
        expiry (see _openbao_request). Returns None (logging the reason) on
        any failure — a missing/late SVID or an unreachable OpenBao must not
        crash-loop the operator, just skip this cycle's OpenBao work."""
        try:
            with open(self.openbao_jwt_path) as f:
                jwt = f.read().strip()
        except OSError as e:
            logger.warning(f"⚠️ Could not read JWT-SVID from {self.openbao_jwt_path}: {e}")
            return None
        if not jwt:
            logger.warning(f"⚠️ JWT-SVID at {self.openbao_jwt_path} is empty (spiffe-helper not ready yet?)")
            return None

        try:
            resp = requests.post(
                f"{self.openbao_addr}/v1/auth/jwt/login",
                json={"role": self.openbao_role, "jwt": jwt},
                timeout=5,
            )
            resp.raise_for_status()
            auth = resp.json()["auth"]
        except (requests.RequestException, KeyError, ValueError) as e:
            logger.error(f"❌ OpenBao jwt login failed (role={self.openbao_role}): {e}")
            return None

        self._openbao_token = auth["client_token"]
        # Refresh a bit before actual expiry so a request never races a token
        # that's valid at read time but expired by the time it reaches OpenBao.
        self._openbao_token_expiry = time.time() + max(auth.get("lease_duration", 0) - 30, 0)
        logger.info(f"✅ OpenBao jwt login OK (role={self.openbao_role})")
        return self._openbao_token

    def _openbao_request(self, method: str, path: str, json_body: Any = None) -> Optional[requests.Response]:
        """Authenticated call to OpenBao's HTTP API (`path` relative to
        /v1/). Logs in (or re-logs-in if the cached token is stale) as
        needed. Returns None — logging the reason — on login failure or a
        request exception; callers treat that the same as any other
        transient-failure case elsewhere in this file (skip, retry next
        reconciliation cycle)."""
        if self._openbao_token is None or time.time() >= self._openbao_token_expiry:
            if self._openbao_login() is None:
                return None
        try:
            resp = requests.request(
                method,
                f"{self.openbao_addr}/v1/{path}",
                headers={"X-Vault-Token": self._openbao_token},
                json=json_body,
                timeout=5,
            )
            return resp
        except requests.RequestException as e:
            logger.error(f"❌ OpenBao request {method} {path} failed: {e}")
            return None

    def _openbao_oidc_accessor(self) -> Optional[str]:
        """The oidc/ auth mount's accessor (cached for the process lifetime).
        Returns None — logging why — if the oidc method isn't enabled yet
        (bootstrap/enable-oidc-sso.sh openbao hasn't been run) or the
        lookup fails; callers treat that as a transient/not-yet-ready
        condition, same as every other _openbao_request failure here."""
        if self._openbao_oidc_accessor_cache:
            return self._openbao_oidc_accessor_cache
        resp = self._openbao_request("GET", "sys/auth")
        if resp is None or not resp.ok:
            logger.error("❌ Could not list OpenBao auth methods to find the oidc/ mount accessor")
            return None
        oidc = resp.json().get("oidc/")
        if not oidc:
            logger.error("❌ No oidc/ auth mount in OpenBao — has bootstrap/enable-oidc-sso.sh openbao been run?")
            return None
        self._openbao_oidc_accessor_cache = oidc["accessor"]
        return self._openbao_oidc_accessor_cache

    def _ensure_openbao_group_alias(self, group_name: str, policy_name: str) -> bool:
        """Ensure an OpenBao external identity group named `group_name`
        carries `policy_name`, aliased to that exact same name on the
        oidc/ mount — so anyone in the Keycloak group of that name (e.g.
        '{namespace}-viewer', already used for k8s RBAC and Argo CD's
        RBAC — see _rbac_policy_block) gets `policy_name` automatically on
        their next OIDC login via the groups claim (groups_claim=groups,
        set up in bootstrap/README.md's OpenBao OIDC section). Mirrors the
        manually-bootstrapped openbao-admins/argocd-admins pattern from
        that same doc, generalized per namespace-role.

        The group write is a natural upsert (name-keyed endpoint); the
        alias write is not — OpenBao 400s on a second create for the same
        mount+name — so the alias is checked for first."""
        resp = self._openbao_request(
            "PUT", f"identity/group/name/{group_name}",
            {"type": "external", "policies": [policy_name]},
        )
        if resp is None or not resp.ok:
            logger.error(
                f"❌ Failed to ensure OpenBao identity group '{group_name}': "
                f"{resp.status_code if resp is not None else 'no response'} "
                f"{resp.text if resp is not None else ''}"
            )
            return False

        resp = self._openbao_request("GET", f"identity/group/name/{group_name}")
        if resp is None or not resp.ok:
            logger.error(f"❌ Could not read back OpenBao identity group '{group_name}'")
            return False
        group = resp.json()["data"]
        alias = group.get("alias")
        if alias and alias.get("name") == group_name:
            return True  # already bound, nothing else to do

        accessor = self._openbao_oidc_accessor()
        if accessor is None:
            return False
        resp = self._openbao_request(
            "POST", "identity/group-alias",
            {"name": group_name, "mount_accessor": accessor, "canonical_id": group["id"]},
        )
        if resp is not None and resp.ok:
            logger.info(f"✅ Bound OpenBao group-alias '{group_name}' -> policy '{policy_name}'")
            return True
        logger.error(
            f"❌ Failed to bind OpenBao group-alias '{group_name}': "
            f"{resp.status_code if resp is not None else 'no response'} "
            f"{resp.text if resp is not None else ''}"
        )
        return False

    def ensure_openbao_access(self, namespace: str) -> bool:
        """Ensure `namespace` has everything both a tenant pod's
        openbao-agent sidecar AND a human logging in via OIDC SSO need to
        reach this namespace's slice of kv: a maintainer (full CRUD)
        ACL policy, a read-only viewer ACL policy, a jwt auth role mapping
        this namespace's SPIFFE IDs to the maintainer policy (workloads
        always get full access — they need to write their own secrets),
        and identity group-aliases mapping the "{namespace}-maintainer" /
        "{namespace}-viewer" Keycloak groups (the same groups already used
        for k8s RBAC and Argo CD's RBAC — see _rbac_policy_block) to those
        same two policies. Plus the agent-config ConfigMap the sidecars
        mount (see apps/security/tenant-guardrails's
        openbao-spiffe-volume-*.yaml). Create-if-missing/leave-as-is-on-
        conflict, same semantics as _apply_namespaced_templates — no drift
        reconciliation of an already-created policy/role/ConfigMap (the
        group-aliases are the one exception, since OpenBao itself 400s on
        a re-create — see _ensure_openbao_group_alias). Returns True only
        if everything is confirmed OK this cycle — a partial success is
        exactly the kind of broken-but-not-obvious state that motivated
        surfacing this as a per-namespace "OpenBaoAccess" condition in the
        first place, so it's reported as not-ready, not silently
        swallowed."""
        ok = True

        try:
            with open(os.path.join(self.OPENBAO_POLICY_TEMPLATES_DIR, "project-maintainer.hcl")) as f:
                maintainer_policy_hcl = f.read().replace("{{ NAMESPACE }}", namespace)
            with open(os.path.join(self.OPENBAO_POLICY_TEMPLATES_DIR, "project-viewer.hcl")) as f:
                viewer_policy_hcl = f.read().replace("{{ NAMESPACE }}", namespace)
        except OSError as e:
            logger.error(f"❌ Could not read OpenBao policy templates: {e}")
            return False

        resp = self._openbao_request(
            "PUT", f"sys/policies/acl/{namespace}-maintainer-policy", {"policy": maintainer_policy_hcl}
        )
        if resp is None:
            return False  # already logged; nothing else in this method can succeed without OpenBao access
        if resp.ok:
            logger.info(f"✅ Ensured OpenBao policy '{namespace}-maintainer-policy'")
        else:
            logger.error(
                f"❌ Failed to write OpenBao maintainer policy for '{namespace}': HTTP {resp.status_code} {resp.text}"
            )
            ok = False

        resp = self._openbao_request(
            "PUT", f"sys/policies/acl/{namespace}-viewer-policy", {"policy": viewer_policy_hcl}
        )
        if resp is not None and resp.ok:
            logger.info(f"✅ Ensured OpenBao policy '{namespace}-viewer-policy'")
        else:
            logger.error(
                f"❌ Failed to write OpenBao viewer policy for '{namespace}': "
                f"HTTP {resp.status_code if resp is not None else 'no response'} {resp.text if resp is not None else ''}"
            )
            ok = False

        try:
            with open(os.path.join(self.OPENBAO_ROLE_TEMPLATES_DIR, "project-maintainer.json")) as f:
                role_body = json.loads(f.read().replace("{{ NAMESPACE }}", namespace))
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"❌ Could not read/parse OpenBao role template: {e}")
            return False
        resp = self._openbao_request("PUT", f"auth/jwt/role/{namespace}", role_body)
        if resp is not None and resp.ok:
            logger.info(f"✅ Ensured OpenBao jwt auth role '{namespace}'")
        else:
            if resp is not None:
                logger.error(f"❌ Failed to write OpenBao role for '{namespace}': HTTP {resp.status_code} {resp.text}")
            ok = False

        if not self._ensure_openbao_group_alias(f"{namespace}-maintainer", f"{namespace}-maintainer-policy"):
            ok = False
        if not self._ensure_openbao_group_alias(f"{namespace}-viewer", f"{namespace}-viewer-policy"):
            ok = False

        try:
            data = {}
            for filename in ("spiffe-helper.conf", "agent.hcl"):
                with open(os.path.join(self.OPENBAO_AGENTCONFIG_TEMPLATES_DIR, filename)) as f:
                    data[filename] = f.read().replace("{{ NAMESPACE }}", namespace)
        except OSError as e:
            logger.error(f"❌ Could not read OpenBao agent-config templates: {e}")
            return False
        configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=self.OPENBAO_AGENT_CONFIGMAP),
            data=data,
        )
        try:
            self.k8s_core_v1.create_namespaced_config_map(namespace, configmap)
            logger.info(f"✅ Created ConfigMap '{self.OPENBAO_AGENT_CONFIGMAP}' in '{namespace}'")
        except ApiException as e:
            if e.status != 409:
                logger.error(f"❌ Failed to create ConfigMap '{self.OPENBAO_AGENT_CONFIGMAP}' in '{namespace}': {e}")
                ok = False
        except Exception as e:
            logger.error(f"❌ Unexpected error creating ConfigMap '{self.OPENBAO_AGENT_CONFIGMAP}' in '{namespace}': {e}")
            ok = False

        return ok

    def _delete_kv_tree(self, path: str) -> bool:
        """Recursively delete every secret under kv/<path>/ - KV v2 has no
        native "delete this whole prefix" call, so list the path then delete
        each leaf, recursing into sub-"directories" (a LIST entry ending in
        '/' is always a nested list, never a leaf secret - same convention
        the OpenBao/Vault CLI and UI use). DELETE .../metadata/<key> removes
        every version of that secret outright (unlike .../data/<key>, a
        soft/recoverable delete of just the latest version) - full teardown
        is the point here, not a reversible one. A 404 on the initial list
        means the path never had anything in it - not an error."""
        resp = self._openbao_request("GET", f"kv/metadata/{path}?list=true")
        if resp is None:
            return False
        if resp.status_code == 404:
            return True
        if not resp.ok:
            logger.error(f"❌ Could not list OpenBao kv/{path} for cleanup: HTTP {resp.status_code} {resp.text}")
            return False

        ok = True
        for key in resp.json().get("data", {}).get("keys", []):
            if key.endswith("/"):
                ok = self._delete_kv_tree(f"{path}/{key.rstrip('/')}") and ok
                continue
            resp2 = self._openbao_request("DELETE", f"kv/metadata/{path}/{key}")
            if resp2 is not None and (resp2.ok or resp2.status_code == 404):
                logger.info(f"✅ Deleted OpenBao secret 'kv/{path}/{key}'")
            else:
                logger.error(
                    f"❌ Failed to delete OpenBao secret 'kv/{path}/{key}': "
                    f"HTTP {resp2.status_code if resp2 is not None else 'no response'} "
                    f"{resp2.text if resp2 is not None else ''}"
                )
                ok = False
        return ok

    def delete_openbao_access(self, namespace: str) -> bool:
        """Tear down everything ensure_openbao_access ever created for
        `namespace`, once its project is deleted: every secret actually
        stored under kv/<namespace>/*, the two ACL policies, the workload
        jwt auth role, and the two identity groups (deleting a group also
        removes its group-alias - there's no separate alias cleanup call).
        Without this, a deleted project's secrets and the access-control
        objects around them linger in OpenBao forever with no UI path back
        to them - the exact gap namespace deletion left for every other
        OpenBao object until now. Best-effort like every other OpenBao call
        here: a transient failure is logged and reported, not raised, so it
        never blocks the k8s namespace deletion itself."""
        ok = self._delete_kv_tree(namespace)

        resp = self._openbao_request("DELETE", f"auth/jwt/role/{namespace}")
        if resp is not None and (resp.ok or resp.status_code == 404):
            logger.info(f"✅ Deleted OpenBao jwt auth role '{namespace}'")
        else:
            logger.error(
                f"❌ Failed to delete OpenBao jwt auth role '{namespace}': "
                f"HTTP {resp.status_code if resp is not None else 'no response'} {resp.text if resp is not None else ''}"
            )
            ok = False

        for suffix in ("maintainer", "viewer"):
            resp = self._openbao_request("DELETE", f"sys/policies/acl/{namespace}-{suffix}-policy")
            if resp is not None and (resp.ok or resp.status_code == 404):
                logger.info(f"✅ Deleted OpenBao policy '{namespace}-{suffix}-policy'")
            else:
                logger.error(
                    f"❌ Failed to delete OpenBao policy '{namespace}-{suffix}-policy': "
                    f"HTTP {resp.status_code if resp is not None else 'no response'} "
                    f"{resp.text if resp is not None else ''}"
                )
                ok = False

            resp = self._openbao_request("DELETE", f"identity/group/name/{namespace}-{suffix}")
            if resp is not None and (resp.ok or resp.status_code == 404):
                logger.info(f"✅ Deleted OpenBao identity group '{namespace}-{suffix}'")
            else:
                logger.error(
                    f"❌ Failed to delete OpenBao identity group '{namespace}-{suffix}': "
                    f"HTTP {resp.status_code if resp is not None else 'no response'} "
                    f"{resp.text if resp is not None else ''}"
                )
                ok = False

        return ok

    def _emit_event(
        self, event_namespace: str, involved_namespace: str, team_id: Optional[str],
        reason: str, message: str, healthy: bool = True,
    ) -> None:
        """Emit a Kubernetes Event whose involvedObject is the
        `involved_namespace` Namespace, stored in `event_namespace` — the
        Teams portal reads these (via teams-api's events_reader.py, a
        cluster-wide query by the team-id label) to show a per-team
        activity feed. `event_namespace` is normally the same as
        `involved_namespace` (so `kubectl get events -n <ns>` keeps working
        naturally), EXCEPT when the involved namespace is being/has been
        deleted and can't hold it — an Event stored *in* a namespace is
        cascade-deleted along with it, so delete_namespace passes
        self.OPERATOR_NAMESPACE instead. Best-effort: a failure to emit an
        Event must never break reconciliation, so this only logs on error.
        Shared low-level primitive for namespace lifecycle events
        (create_namespace/delete_namespace) and provisioning-condition
        transitions (update_namespace_status)."""
        now = datetime.now(timezone.utc)
        labels = {self.EVENT_TEAM_LABEL: team_id} if team_id else {}
        body = client.CoreV1Event(
            metadata=client.V1ObjectMeta(generate_name=f"teams-operator-{involved_namespace}-", labels=labels),
            involved_object=client.V1ObjectReference(
                kind="Namespace", name=involved_namespace, namespace=involved_namespace, api_version="v1"
            ),
            reason=reason,
            message=message,
            type="Normal" if healthy else "Warning",
            source=client.V1EventSource(component="teams-operator"),
            first_timestamp=now,
            last_timestamp=now,
            count=1,
        )
        try:
            self.k8s_core_v1.create_namespaced_event(event_namespace, body)
        except ApiException as e:
            logger.error(f"❌ Failed to emit Event ({reason}) for '{involved_namespace}': {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error emitting Event ({reason}) for '{involved_namespace}': {e}")

    def _emit_condition_event(self, namespace: str, team_id: str, cond_type: str, healthy: bool) -> None:
        """Build the reason/message for a provisioning condition's
        transition and emit it — see _emit_event."""
        label = self.CONDITION_LABELS.get(cond_type, cond_type)
        reason = f"{cond_type}Ready" if healthy else f"{cond_type}Failed"
        message = f"{label} is now ready" if healthy else f"{label} failed to provision"
        self._emit_event(namespace, namespace, team_id, reason, message, healthy)

    def _emit_cluster_event(self, name: str, reason: str, message: str, healthy: bool = True) -> None:
        """Emit an Event for a cluster-scoped action with no owning
        team/namespace to attach to (e.g. the cluster-admin
        ClusterRoleBinding sync, which applies to whichever Keycloak users
        currently hold the `admin` realm role - not any single team). No
        team-id label (there's no team), so this can't appear in the
        per-team activity feed - it's still emitted (satisfies "every
        cluster action gets an Event"), visible via `kubectl get events -n
        <this operator's namespace>`, but the Teams portal has no
        cluster-wide activity view today to show it in."""
        now = datetime.now(timezone.utc)
        body = client.CoreV1Event(
            metadata=client.V1ObjectMeta(generate_name=f"teams-operator-{name}-"),
            involved_object=client.V1ObjectReference(
                kind="ClusterRoleBinding", name=name, api_version="rbac.authorization.k8s.io/v1"
            ),
            reason=reason,
            message=message,
            type="Normal" if healthy else "Warning",
            source=client.V1EventSource(component="teams-operator"),
            first_timestamp=now,
            last_timestamp=now,
            count=1,
        )
        try:
            self.k8s_core_v1.create_namespaced_event(self.OPERATOR_NAMESPACE, body)
        except ApiException as e:
            logger.error(f"❌ Failed to emit Event ({reason}) for ClusterRoleBinding '{name}': {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error emitting Event ({reason}) for ClusterRoleBinding '{name}': {e}")

    def update_namespace_status(self, namespace: str, team_id: str, results: Dict[str, bool]) -> None:
        """Write a Kubernetes-condition-shaped summary of this reconcile
        cycle's outcome onto the namespace itself, as a JSON-encoded list on
        the `teams.example.com/provisioning-status` annotation — one entry
        per concern (RBAC, ImagePullAccess, ResourceQuota, LimitRange,
        NetworkPolicy, OpenBaoAccess), each `{type, status, reason,
        lastTransitionTime, lastCheckedTime}`. teams-api reads this directly
        (it already has its own K8s client — see compliance.py's identical
        pattern) to expose a per-namespace status badge in the Teams portal.

        `lastTransitionTime` only moves when status actually flips, same
        convention as Pod/Deployment conditions — `lastCheckedTime` moves
        every cycle regardless, so "stuck on Unknown because the operator
        itself has been down" is distinguishable from "stable and healthy"."""
        now = datetime.now(timezone.utc).isoformat()

        existing_by_type: Dict[str, Dict[str, Any]] = {}
        try:
            ns = self.k8s_core_v1.read_namespace(namespace)
            raw = (ns.metadata.annotations or {}).get(self.STATUS_ANNOTATION)
            if raw:
                existing_by_type = {c["type"]: c for c in json.loads(raw)}
        except (ApiException, Exception) as e:
            logger.warning(f"⚠️ Could not read existing provisioning-status on '{namespace}' (will overwrite): {e}")

        conditions = []
        for cond_type, healthy in results.items():
            status = "True" if healthy else "False"
            prev = existing_by_type.get(cond_type)
            transitioned = not prev or prev.get("status") != status
            last_transition = now if transitioned else prev.get("lastTransitionTime", now)
            conditions.append({
                "type": cond_type,
                "status": status,
                "reason": "ReconcileSucceeded" if healthy else "ReconcileFailed",
                "lastTransitionTime": last_transition,
                "lastCheckedTime": now,
            })
            # Only emit an Event on an actual flip, not every ~30s reconcile
            # pass — otherwise a namespace sitting healthy forever would
            # accumulate a duplicate "ready" Event on every cycle, drowning
            # out anything worth a team lead's attention.
            if transitioned:
                self._emit_condition_event(namespace, team_id, cond_type, healthy)

        try:
            self.k8s_core_v1.patch_namespace(
                namespace, {"metadata": {"annotations": {self.STATUS_ANNOTATION: json.dumps(conditions)}}}
            )
        except ApiException as e:
            logger.error(f"❌ Failed to write provisioning-status on '{namespace}': {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error writing provisioning-status on '{namespace}': {e}")

    def create_namespace(self, team_id: str, team_name: str, namespace_name: str) -> bool:
        """Create a Kubernetes namespace for the team"""
        try:
            # Define namespace metadata
            namespace_body = client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name=namespace_name,
                    labels={
                        "app.kubernetes.io/managed-by": "teams-operator",
                        "teams.example.com/team-id": team_id,
                        "teams.example.com/team-name": team_name.replace(" ", "-").lower()
                    },
                    annotations={
                        "teams.example.com/original-team-name": team_name,
                        "teams.example.com/created-by": "teams-operator",
                        "teams.example.com/team-id": team_id
                    }
                )
            )
            
            # Create the namespace
            self.k8s_core_v1.create_namespace(body=namespace_body)
            logger.info(f"✅ Created namespace '{namespace_name}' for team '{team_name}' (ID: {team_id})")
            self._emit_event(namespace_name, namespace_name, team_id, "NamespaceProvisioned",
                              f"Namespace provisioned for team '{team_name}'")
            return True
            
        except ApiException as e:
            if e.status == 409:  # Namespace already exists
                logger.warning(f"⚠️ Namespace '{namespace_name}' already exists")
                return True
            else:
                logger.error(f"❌ Failed to create namespace '{namespace_name}': {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Unexpected error creating namespace: {e}")
            return False
    
    def delete_namespace(self, namespace_name: str, team_name: str, team_id: str) -> bool:
        """Delete a Kubernetes namespace when team is removed, and tear down
        everything this operator ever provisioned for it in OpenBao - secrets,
        policies, the jwt role, identity groups (see delete_openbao_access).
        Two independent systems: OpenBao cleanup runs regardless of which k8s
        outcome below is hit, including "already deleted" (a previous cycle
        may have removed the namespace but failed partway through OpenBao
        cleanup, e.g. a transient OpenBao outage) - only the two real k8s
        error paths short-circuit past it, since retrying next cycle covers
        both halves anyway."""
        openbao_ok = self.delete_openbao_access(namespace_name)
        try:
            self.k8s_core_v1.delete_namespace(name=namespace_name)
            logger.info(f"🗑️ Deleted namespace '{namespace_name}' for removed team '{team_name}'")
            # Stored in this operator's own namespace, NOT namespace_name -
            # that namespace is being torn down right now, and an Event
            # stored inside it would be cascade-deleted along with it,
            # never reaching the UI. See _emit_event.
            self._emit_event(self.OPERATOR_NAMESPACE, namespace_name, team_id,
                              "NamespaceDeleted", f"Namespace deleted for team '{team_name}'")
            return openbao_ok
        except ApiException as e:
            if e.status == 404:  # Namespace doesn't exist
                logger.warning(f"⚠️ Namespace '{namespace_name}' not found (already deleted?)")
                return openbao_ok
            else:
                logger.error(f"❌ Failed to delete namespace '{namespace_name}': {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Unexpected error deleting namespace: {e}")
            return False
    
    async def reconcile_teams(self):
        """Main reconciliation loop - sync teams with namespaces"""
        teams = await self.fetch_teams()

        # None => the API was unreachable/errored. Skip this cycle entirely so a
        # transient outage never prunes namespaces. (An empty list, by contrast,
        # is a real "no teams" state and is reconciled normally.)
        if teams is None:
            logger.warning("Skipping reconciliation: teams could not be fetched from the API")
            return

        current_teams = {team['id']: team for team in teams}
        current_team_ids = set(current_teams.keys())
        changed = False

        # Reconcile each existing team's desired namespace set. `namespaces` is
        # authoritative and can legitimately be empty (a team whose only/default
        # namespace was deleted) — that just means nothing is provisioned for it,
        # not a signal to invent a fallback namespace the API never asked for.
        for team_id, team in current_teams.items():
            team_name = team['name']
            desired = set(team.get('namespaces') or [])
            provisioned = self.team_namespaces.setdefault(team_id, set())

            for namespace_name in desired - provisioned:      # newly wanted
                if self.create_namespace(team_id, team_name, namespace_name):
                    provisioned.add(namespace_name)
                    changed = True

            for namespace_name in provisioned - desired:      # no longer wanted
                if self.delete_namespace(namespace_name, team_name, team_id):
                    provisioned.discard(namespace_name)
                    changed = True

        # Handle deleted teams (remove all of their namespaces).
        deleted_teams = set(self.team_namespaces) - current_team_ids
        for team_id in deleted_teams:
            team_name = f"team-{team_id}"  # fallback; the team record is gone
            for namespace_name in list(self.team_namespaces[team_id]):
                if self.delete_namespace(namespace_name, team_name, team_id):
                    self.team_namespaces[team_id].discard(namespace_name)
            if not self.team_namespaces[team_id]:
                del self.team_namespaces[team_id]
                changed = True

        # Clean up Argo CD Project state (Applications + AppProject + rbac
        # policy block) for any project this operator was tracking that's no
        # longer present - tracked via _project_slugs rather than
        # deleted_teams above, since a project can still hold slug-tracking
        # state after its namespace set has already emptied out on its own.
        # Applications first (see delete_argocd_applications) - deleting the
        # AppProject doesn't cascade-delete the Applications that reference
        # it, so without this they'd be orphaned in the argocd namespace.
        for team_id in set(self._project_slugs) - current_team_ids:
            slug = self._project_slugs[team_id]
            apps_ok = self.delete_argocd_applications(slug)
            appproject_ok = self.delete_argocd_appproject(slug)
            rbac_ok = self._remove_rbac_policy_block(slug)
            if apps_ok and appproject_ok and rbac_ok:
                del self._project_slugs[team_id]
                self._last_project_state.pop(team_id, None)
                self._emit_project_event(team_id, "ProjectDeprovisioned", f"Argo CD project '{slug}' removed")

        if changed:
            total_ns = sum(len(v) for v in self.team_namespaces.values())
            logger.info(f"📊 Reconciliation complete: {len(current_teams)} teams, {total_ns} namespaces")

        # RBAC sync, part 1: ensure each namespace we manage has its two
        # static Group-bound RoleBindings (see sync_namespace_rbac) — this
        # needs nothing from teams-api beyond the namespace name itself, so
        # it doesn't depend on /internal/access succeeding. A namespace just
        # deleted above is skipped too — no RoleBindings to ensure for a
        # namespace that no longer exists, and its old ones went with it
        # (namespace-scoped, cascade-deleted).
        for team_id, provisioned in self.team_namespaces.items():
            for namespace_name in provisioned:
                rbac_ok = self.sync_namespace_rbac(namespace_name)
                pull_secret_ok = self.ensure_harbor_pull_secret(namespace_name)
                sa_ok = self.ensure_default_sa_pull_secret(namespace_name)
                quotas_ok = self.ensure_priority_quotas(namespace_name)
                limits_ok = self.ensure_limit_ranges(namespace_name)
                netpol_ok = self.ensure_network_policies(namespace_name)
                openbao_ok = self.ensure_openbao_access(namespace_name)
                # Surfaced in the Teams portal as a per-namespace status badge
                # (teams-api reads this annotation directly) — see
                # update_namespace_status's docstring for why this is a
                # point-in-time snapshot, not live monitoring.
                self.update_namespace_status(namespace_name, team_id, {
                    "RBAC": rbac_ok,
                    "ImagePullAccess": pull_secret_ok and sa_ok,
                    "ResourceQuota": quotas_ok,
                    "LimitRange": limits_ok,
                    "NetworkPolicy": netpol_ok,
                    "OpenBaoAccess": openbao_ok,
                })

        # Argo CD self-service Project reconciliation: the AppProject CRD and
        # this project's argocd-rbac-cm policy block (whose `g,` lines bind
        # directly to the project's namespaces' existing k8s RBAC groups -
        # see _rbac_policy_block - no separate Keycloak groups of our own to
        # create or sync). One iteration per *project* (not per namespace,
        # unlike the loop above). Reuses the `teams` list fetch_teams
        # already returned this cycle, no extra API call.
        for team_id, team in current_teams.items():
            argocd_project = team.get('argocd_project')
            if not argocd_project:
                continue  # teams-api not yet returning this field (mid-rollout)
            self._project_slugs[team_id] = argocd_project

            namespaces = set(team.get('namespaces') or [])
            source_repos = tuple(sorted(team.get('source_repos') or []))
            state_key = (frozenset(namespaces), source_repos)
            if self._last_project_state.get(team_id) == state_key:
                continue  # nothing this operator manages has changed

            appproject_ok = self.ensure_argocd_appproject(argocd_project, namespaces, list(source_repos))
            rbac_ok = self.ensure_argocd_rbac_policy(argocd_project, namespaces)

            if appproject_ok and rbac_ok:
                self._last_project_state[team_id] = state_key
                self._emit_project_event(
                    team_id, "ProjectProvisioned",
                    f"Argo CD project '{argocd_project}' provisioned "
                    f"({len(namespaces)} namespace(s), {len(source_repos)} source repo(s))",
                )
            else:
                self._emit_project_event(
                    team_id, "ProjectProvisionFailed",
                    f"Argo CD project '{argocd_project}' provisioning incomplete "
                    f"(appproject={appproject_ok}, rbac={rbac_ok})",
                    healthy=False,
                )

        # RBAC sync, part 2: the one binding that's still user-list-based —
        # cluster-admin for Keycloak `admin`-role holders. A single cluster-
        # wide object, never part of the per-namespace proliferation this
        # design otherwise avoids, so it's not worth a Keycloak-group
        # indirection of its own.
        access = await self.fetch_access()
        if access is None:
            logger.warning("Skipping admin ClusterRoleBinding sync: access could not be fetched from the API")
            return

        admins = access.get("admins")
        if admins is None:
            logger.warning("Skipping admin ClusterRoleBinding sync: admin list unknown (Keycloak unreachable?)")
        else:
            self.sync_admin_binding(admins)

    async def run(self):
        """Main operator loop"""
        logger.info(f"🚀 Teams Operator starting...")
        logger.info(f"📡 Teams API URL: {self.teams_api_url}")
        logger.info(f"⏰ Poll interval: {self.poll_interval} seconds")
        
        # Initial reconciliation
        await self.reconcile_teams()
        
        # Main loop
        while True:
            try:
                await asyncio.sleep(self.poll_interval)
                await self.reconcile_teams()
            except KeyboardInterrupt:
                logger.info("👋 Received shutdown signal, exiting...")
                break
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                await asyncio.sleep(self.poll_interval)

async def main():
    """Entry point"""
    operator = TeamsOperator()
    await operator.run()

if __name__ == "__main__":
    asyncio.run(main())
