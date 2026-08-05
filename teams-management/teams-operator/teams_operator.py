#!/usr/bin/env python3
"""
Teams Operator - Creates Kubernetes namespaces when teams are created in the Teams API
"""

import asyncio
import glob
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Set, Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse
import aiohttp
import jwt
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

        # GitHub App repo credentials (see docs/self-service-repos-github-app.md).
        # The legacy single *platform* App id + private key live in OpenBao at
        # OPENBAO_GITHUB_APP_PATH (a KV-v2 data path, so it includes /data/). Each
        # per-project registered *connection* stores its own App key at
        # kv/data/platform/github-apps/<connection-id> (see _openbao_github_app_path).
        # This operator reads them (platform-operator-policy) to (a) enumerate a
        # connected installation's repos and (b) materialize Argo CD githubApp repo
        # credentials. _github_app_creds_cache caches (id, key) per connection key
        # (None = the platform App) for the process lifetime.
        self.openbao_github_app_path = os.getenv(
            "OPENBAO_GITHUB_APP_PATH", "kv/data/platform/github-app"
        )
        # Per-connection App keys live under here (one KV entry per connection id).
        self.openbao_github_apps_prefix = os.getenv(
            "OPENBAO_GITHUB_APPS_PREFIX", "kv/data/platform/github-apps"
        )
        self._github_app_creds_cache: Dict[Optional[str], Tuple[str, str]] = {}

        # --- Keycloak realm-write reconcile (GATED OFF by default) ------------
        # When KC_RECONCILE_ENABLED=true, teams-operator becomes the SOLE writer
        # of the Keycloak {ns}-viewer/-maintainer groups, project-<slug>-owner
        # groups, and the project-manager realm role — reconciled from
        # /internal/access (see reconcile_keycloak). Until cutover it stays off
        # and teams-api keeps doing those writes. The admin client_secret is read
        # from OpenBao via this pod's SPIFFE identity (no static k8s secret).
        self.kc_reconcile_enabled = os.getenv("KC_RECONCILE_ENABLED", "false").lower() == "true"
        self.kc_base_url = os.getenv(
            "KEYCLOAK_ADMIN_BASE_URL", "http://keycloak-keycloakx-http.keycloak.svc/auth"
        ).rstrip("/")
        self.kc_realm = os.getenv("KEYCLOAK_REALM", "teams")
        self.kc_client_id = os.getenv("KEYCLOAK_ADMIN_CLIENT_ID", "teams-operator-kc-admin")
        self.kc_secret_openbao_path = os.getenv(
            "KEYCLOAK_ADMIN_OPENBAO_PATH", "kv/data/platform/keycloak-admin"
        )
        self.kc_pm_role = os.getenv("KEYCLOAK_PM_ROLE", "project-manager")
        self._kc_token: Optional[str] = None
        self._kc_token_expiry: float = 0.0
        self._kc_group_ids: Dict[str, str] = {}

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
        # --- How we authenticate to teams-api /internal/* (A1) ----------------
        # "keycloak" (default): teams-operator-sa client-credentials token.
        # "svid": present this pod's SPIRE JWT-SVID (audience "teams-api",
        #   written by the spiffe-helper sidecar) — no Keycloak, no static
        #   secret. Flip together with teams-api's INTERNAL_AUTH_MODE.
        self.teams_api_auth = os.getenv("TEAMS_API_AUTH", "keycloak").strip().lower()
        self.teams_api_svid_path = os.getenv("TEAMS_API_SVID_PATH", "/operator-shared/teams-api-jwt")

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

    def _teams_api_svid(self) -> Optional[str]:
        """This pod's SPIRE JWT-SVID for calling teams-api /internal/* (audience
        "teams-api", written by the spiffe-helper sidecar — see the operator
        deployment). None (logging why) if it's missing/empty, so callers skip
        this cycle and retry, same as the Keycloak-token path."""
        try:
            with open(self.teams_api_svid_path) as f:
                svid = f.read().strip()
        except OSError as e:
            logger.warning(f"⚠️ Could not read teams-api JWT-SVID from {self.teams_api_svid_path}: {e}")
            return None
        if not svid:
            logger.warning(f"⚠️ teams-api JWT-SVID at {self.teams_api_svid_path} is empty (spiffe-helper not ready yet?)")
            return None
        return svid

    def _api_auth_headers(self) -> Dict[str, str]:
        if self.teams_api_auth == "svid":
            svid = self._teams_api_svid()
            return {"Authorization": f"Bearer {svid}"} if svid else {}
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

    # --- GitHub App repo credentials -----------------------------------------
    # Argo CD has no native OpenBao integration for repo creds; it reads them
    # only from k8s Secrets in the argocd namespace labelled
    # argocd.argoproj.io/secret-type: repository. For each repo a project
    # connected through the platform GitHub App (teams-api records the
    # installation_id), this operator reads the App id + private key from OpenBao
    # (kv/platform/github-app) and materializes such a Secret with Argo CD's
    # githubApp fields — Argo CD then mints its own short-lived installation
    # tokens. See docs/self-service-repos-github-app.md.

    def _openbao_github_app_path(self, connection_id: Optional[str]) -> str:
        """The KV-v2 data path holding an App key: the legacy platform App when
        connection_id is falsy, else the per-connection entry."""
        if not connection_id:
            return self.openbao_github_app_path
        return f"{self.openbao_github_apps_prefix}/{connection_id}"

    def _github_app_creds(self, connection_id: Optional[str] = None) -> Optional[Tuple[str, str]]:
        """(app_id, private_key) from OpenBao for a connection (None = the platform
        App), cached per-connection for the process lifetime. Returns None —
        logging why — if the secret isn't present yet (the App hasn't been
        registered/seeded) or OpenBao is unreachable; callers treat that as
        "can't materialize this cycle", same as any transient failure."""
        key = connection_id or None
        cached = self._github_app_creds_cache.get(key)
        if cached:
            return cached
        path = self._openbao_github_app_path(connection_id)
        resp = self._openbao_request("GET", path)
        if resp is None or not resp.ok:
            logger.error(
                "❌ Could not read GitHub App creds from OpenBao "
                f"({path}): {resp.status_code if resp is not None else 'no response'}"
            )
            return None
        data = (resp.json().get("data") or {}).get("data") or {}
        app_id, private_key = data.get("app_id"), data.get("private_key")
        if not app_id or not private_key:
            logger.error(
                f"❌ GitHub App secret at {path} is missing 'app_id' and/or 'private_key' keys"
            )
            return None
        creds = (str(app_id), str(private_key))
        self._github_app_creds_cache[key] = creds
        return creds

    def _github_installation_repos(
        self, installation_id: str, connection_id: Optional[str] = None
    ) -> Optional[List[str]]:
        """The HTTPS clone URLs an installation grants — the operator side of the
        Option-B flow: teams-api records a pending connection (it has no App key),
        the operator resolves it here using the App key from OpenBao for the
        connection that minted it (None = the platform App). Mints an App JWT ->
        installation token -> lists repos (paginated). Returns None (logging why)
        on any failure so resolve_github_connections leaves the pending row for a
        retry next cycle."""
        creds = self._github_app_creds(connection_id)
        if creds is None:
            return None
        app_id, private_key = creds
        try:
            now = int(time.time())
            app_jwt = jwt.encode(
                {"iat": now - 60, "exp": now + 9 * 60, "iss": app_id},
                private_key, algorithm="RS256",
            )
        except Exception as e:  # noqa: BLE001 - a bad key must not crash the loop
            logger.error(f"❌ Could not sign GitHub App JWT: {e}")
            return None

        api = "https://api.github.com"
        common = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        try:
            resp = requests.post(
                f"{api}/app/installations/{installation_id}/access_tokens",
                headers={**common, "Authorization": f"Bearer {app_jwt}"}, timeout=10,
            )
            if resp.status_code != 201:
                logger.error(f"❌ GitHub installation token {resp.status_code}: {resp.text}")
                return None
            inst_token = resp.json().get("token")
            if not inst_token:
                logger.error("❌ GitHub installation token response had no token")
                return None

            urls: List[str] = []
            page = 1
            while True:
                resp = requests.get(
                    f"{api}/installation/repositories",
                    headers={**common, "Authorization": f"token {inst_token}"},
                    params={"per_page": 100, "page": page}, timeout=10,
                )
                if resp.status_code != 200:
                    logger.error(f"❌ GitHub list repositories {resp.status_code}: {resp.text}")
                    return None
                repos = resp.json().get("repositories", [])
                for r in repos:
                    clone = r.get("clone_url") or (
                        (r.get("html_url") or "") + ".git" if r.get("html_url") else None
                    )
                    if clone:
                        urls.append(clone)
                if len(repos) < 100:
                    break
                page += 1
            return urls
        except requests.RequestException as e:
            logger.error(f"❌ GitHub API call failed (installation {installation_id}): {e}")
            return None

    @staticmethod
    def _account_prefix(repo_url: str) -> Optional[str]:
        """The owner/account URL prefix of a GitHub repo URL, e.g.
        https://github.com/rkdutta/foo.git -> https://github.com/rkdutta. Argo CD
        matches a repo-creds credential template by longest URL prefix, so one
        credential per account (not per repo) covers every repo under it."""
        try:
            p = urlparse(repo_url)
            owner = p.path.lstrip("/").split("/", 1)[0]
            if not p.scheme or not p.netloc or not owner:
                return None
            return f"{p.scheme}://{p.netloc}/{owner}"
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _repo_creds_name(prefix: str) -> str:
        return f"github-app-creds-{hashlib.sha1(prefix.encode()).hexdigest()[:10]}"

    def reconcile_github_repo_creds(self, current_teams: Dict[str, dict]) -> bool:
        """Cluster-wide: one Argo CD githubApp `repo-creds` credential template per
        (account-prefix, installation) for repos connected through the legacy single
        *platform* App (connection_id == '') — the global whitelist and any repo not
        bound to a per-project connection. A single copy of the platform App key per
        account, not one per repo. Repos bound to a registered per-project connection
        are handled by ensure_connection_repo_credentials (per-repo `repository`
        secrets), since two connections can cover the same account prefix and a
        prefix template can't disambiguate them. Prunes managed repo-creds no longer
        desired. See docs/self-service-repos-github-app.md."""
        # prefix -> installation_id, deduped across every project. Platform-App
        # (connection-less) repos only; connection-bound repos are per-repo.
        desired: Dict[str, str] = {}
        for team in current_teams.values():
            for r in team.get("repo_installations") or []:
                if r.get("connection_id"):
                    continue  # handled per-repo by ensure_connection_repo_credentials
                prefix = self._account_prefix(r.get("repo_url", ""))
                if prefix and r.get("installation_id"):
                    desired[prefix] = str(r["installation_id"])

        ok = True
        creds = self._github_app_creds() if desired else None
        if desired and creds is None:
            ok = False  # can't materialize this cycle; still prune below
        elif desired:
            app_id, private_key = creds
            for prefix, installation_id in desired.items():
                name = self._repo_creds_name(prefix)
                body = client.V1Secret(
                    metadata=client.V1ObjectMeta(
                        name=name,
                        namespace=self.ARGOCD_NAMESPACE,
                        labels={
                            "argocd.argoproj.io/secret-type": "repo-creds",
                            "app.kubernetes.io/managed-by": "teams-operator",
                            "teams-operator/github-repo-creds": "true",
                        },
                    ),
                    string_data={
                        "type": "git",
                        "url": prefix,
                        "githubAppID": app_id,
                        "githubAppInstallationID": installation_id,
                        "githubAppPrivateKey": private_key,
                    },
                )
                try:
                    self.k8s_core_v1.create_namespaced_secret(self.ARGOCD_NAMESPACE, body)
                    logger.info(f"✅ Created Argo CD repo-creds '{name}' for '{prefix}'")
                except ApiException as e:
                    if e.status == 409:
                        try:
                            self.k8s_core_v1.replace_namespaced_secret(name, self.ARGOCD_NAMESPACE, body)
                        except ApiException as re:
                            logger.error(f"❌ Failed to update repo-creds '{name}': {re}")
                            ok = False
                    else:
                        logger.error(f"❌ Failed to create repo-creds '{name}': {e}")
                        ok = False

        # Prune our repo-creds no longer desired (label-scoped, so operator
        # restarts don't need in-memory tracking).
        desired_names = {self._repo_creds_name(p) for p in desired}
        try:
            existing = self.k8s_core_v1.list_namespaced_secret(
                self.ARGOCD_NAMESPACE, label_selector="teams-operator/github-repo-creds=true"
            )
        except ApiException as e:
            logger.error(f"❌ Could not list managed repo-creds for pruning: {e}")
            return False
        for s in existing.items:
            if s.metadata.name not in desired_names:
                if self._delete_repo_secret(s.metadata.name):
                    logger.info(f"🗑️ Pruned stale Argo CD repo-creds '{s.metadata.name}'")
                else:
                    ok = False
        return ok

    def _delete_repo_secret(self, name: str) -> bool:
        try:
            self.k8s_core_v1.delete_namespaced_secret(name, self.ARGOCD_NAMESPACE)
            return True
        except ApiException as e:
            if e.status == 404:
                return True
            logger.error(f"❌ Failed to delete Argo CD repo credential '{name}': {e}")
            return False

    @staticmethod
    def _conn_repo_secret_name(repo_url: str) -> str:
        """Deterministic name for a per-repo `repository` Secret (connection-bound
        repos). Exact-URL match, so it beats any account-prefix `repo-creds`."""
        return f"github-app-repo-{hashlib.sha1(repo_url.encode()).hexdigest()[:12]}"

    def ensure_connection_repo_credentials(self, current_teams: Dict[str, dict]) -> bool:
        """Per-repo Argo CD `repository` Secrets for repos connected through a
        registered per-project connection. Unlike the account-level `repo-creds`
        templates (reconcile_github_repo_creds), these match an EXACT repo URL, so
        two projects' connections covering the same GitHub account never collide —
        Argo CD prefers the exact-URL `repository` entry over any prefix template.
        One Secret per connected repo, keyed by the repo URL; the App id + key come
        from the repo's connection (app_id via /internal/teams, key from OpenBao
        kv/platform/github-apps/<connection-id>). Prunes stale ones by label."""
        # repo_url -> (installation_id, connection_id, app_id)
        desired: Dict[str, Tuple[str, str, str]] = {}
        for team in current_teams.values():
            conn_app_id = {
                c.get("id"): str(c.get("app_id", ""))
                for c in (team.get("github_connections") or [])
            }
            for r in team.get("repo_installations") or []:
                conn_id = r.get("connection_id")
                url, inst = r.get("repo_url", ""), r.get("installation_id", "")
                if not conn_id or not url or not inst:
                    continue
                app_id = conn_app_id.get(conn_id, "")
                if not app_id:
                    # Connection not ready yet (no app_id) — skip; a later cycle
                    # materializes it once teams-operator has resolved the registration.
                    continue
                desired[url] = (str(inst), str(conn_id), app_id)

        ok = True
        # Cache keys per connection so we read each App key from OpenBao once.
        for url, (installation_id, connection_id, app_id) in desired.items():
            creds = self._github_app_creds(connection_id)
            if creds is None:
                ok = False  # key unreadable this cycle; leave for retry, still prune
                continue
            _, private_key = creds
            name = self._conn_repo_secret_name(url)
            body = client.V1Secret(
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=self.ARGOCD_NAMESPACE,
                    labels={
                        "argocd.argoproj.io/secret-type": "repository",
                        "app.kubernetes.io/managed-by": "teams-operator",
                        "teams-operator/github-conn-repo": "true",
                    },
                ),
                string_data={
                    "type": "git",
                    "url": url,
                    "githubAppID": app_id,
                    "githubAppInstallationID": installation_id,
                    "githubAppPrivateKey": private_key,
                },
            )
            try:
                self.k8s_core_v1.create_namespaced_secret(self.ARGOCD_NAMESPACE, body)
                logger.info(f"✅ Created Argo CD repository secret '{name}' for '{url}'")
            except ApiException as e:
                if e.status == 409:
                    try:
                        self.k8s_core_v1.replace_namespaced_secret(name, self.ARGOCD_NAMESPACE, body)
                    except ApiException as re:
                        logger.error(f"❌ Failed to update repository secret '{name}': {re}")
                        ok = False
                else:
                    logger.error(f"❌ Failed to create repository secret '{name}': {e}")
                    ok = False

        # Prune per-repo secrets no longer desired (label-scoped).
        desired_names = {self._conn_repo_secret_name(u) for u in desired}
        try:
            existing = self.k8s_core_v1.list_namespaced_secret(
                self.ARGOCD_NAMESPACE, label_selector="teams-operator/github-conn-repo=true"
            )
        except ApiException as e:
            logger.error(f"❌ Could not list managed repository secrets for pruning: {e}")
            return False
        for s in existing.items:
            if s.metadata.name not in desired_names:
                if self._delete_repo_secret(s.metadata.name):
                    logger.info(f"🗑️ Pruned stale Argo CD repository secret '{s.metadata.name}'")
                else:
                    ok = False
        return ok

    async def resolve_github_registrations(self):
        """Convert pending GitHub App-Manifest registrations teams-api recorded:
        for each {connection_id, code}, exchange the one-time code with GitHub for
        the new App's id/slug/name + private key, write the key to OpenBao
        (kv/platform/github-apps/<connection-id>), and report the non-secret
        identifiers back so teams-api flips the connection to 'ready'. This is why
        teams-api never holds an App key — the conversion response (which carries
        the key) is received here, in the component that owns OpenBao writes.
        Best-effort: a failure leaves the pending row for the next cycle."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.teams_api_url}/internal/github-registrations",
                    headers=self._api_auth_headers(),
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to fetch pending github-registrations: HTTP {resp.status}")
                        return
                    pending = await resp.json()

                for reg in pending:
                    connection_id, code = reg.get("connection_id"), reg.get("code")
                    if not connection_id or not code:
                        continue
                    app = self._exchange_manifest_code(code)
                    if app == self._MANIFEST_TERMINAL:
                        # Dead code (invalid/expired/consumed) — abandon so we don't
                        # retry it forever; the user must re-register.
                        await self._abandon_registration(session, connection_id)
                        continue
                    if app is None:
                        continue  # transient; leave pending for retry (code valid ~1h)
                    if not self._store_connection_app_key(connection_id, app):
                        # The single-use code was already consumed by the conversion
                        # above, so the key is unrecoverable — abandon rather than
                        # loop on a code that will now only 404.
                        logger.error(
                            f"❌ App key store failed after conversion for '{connection_id}'; "
                            "abandoning (re-registration required)"
                        )
                        await self._abandon_registration(session, connection_id)
                        continue
                    async with session.post(
                        f"{self.teams_api_url}/internal/github-registrations/resolve",
                        headers=self._api_auth_headers(),
                        json={
                            "connection_id": connection_id,
                            "app_id": str(app.get("id", "")),
                            "slug": app.get("slug", ""),
                            "name": app.get("name", ""),
                        },
                    ) as rresp:
                        if rresp.status == 200:
                            logger.info(
                                f"✅ Registered GitHub App connection '{connection_id}' "
                                f"(app '{app.get('slug')}')"
                            )
                        else:
                            logger.error(f"Failed to resolve github-registration: HTTP {rresp.status}")
        except aiohttp.ClientError as e:
            logger.error(f"Error resolving github-registrations: {e}")
        except Exception as e:  # noqa: BLE001 - must not kill the reconcile loop
            logger.error(f"Unexpected error resolving github-registrations: {e}")

    # Sentinel: the manifest code can't be converted and never will (invalid,
    # expired, or already consumed). Distinct from None (a transient failure worth
    # retrying) because a manifest code is SINGLE-USE — re-POSTing a consumed one
    # just 404s forever, so the registration must be abandoned, not retried.
    _MANIFEST_TERMINAL = "terminal"

    def _exchange_manifest_code(self, code: str):
        """POST GitHub's App-Manifest conversion: code -> {id, slug, name, pem,...}.
        Returns the App dict on success, `_MANIFEST_TERMINAL` when the code is
        invalid/expired/consumed (a 4xx that won't change on retry), or None on a
        transient error (retry next cycle). The `pem` is the new App's private key
        — handled only here, written straight to OpenBao."""
        try:
            resp = requests.post(
                f"https://api.github.com/app-manifests/{code}/conversions",
                headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
                timeout=15,
            )
            if resp.status_code == 201:
                app = resp.json()
                if not app.get("id") or not app.get("pem"):
                    logger.error("❌ GitHub manifest conversion 201 but missing id/pem; abandoning")
                    return self._MANIFEST_TERMINAL
                return app
            if resp.status_code in (404, 410, 422):
                logger.error(
                    f"❌ GitHub manifest code invalid/expired/already-used "
                    f"({resp.status_code}); abandoning registration"
                )
                return self._MANIFEST_TERMINAL
            # 5xx / rate-limit / auth blips: transient, retry next cycle.
            logger.error(f"❌ GitHub manifest conversion {resp.status_code}: {resp.text[:200]}")
            return None
        except requests.RequestException as e:
            logger.error(f"❌ GitHub manifest conversion call failed: {e}")
            return None

    def _store_connection_app_key(self, connection_id: str, app: dict) -> bool:
        """Write a newly-created connection App's id + private key to OpenBao at
        kv/platform/github-apps/<connection-id> (KV-v2 data path). Retries a few
        times in-cycle: the manifest code is already consumed by the time we get
        here, so the key exists only in memory this cycle — a transient OpenBao
        blip must be ridden out now, not deferred (a next-cycle retry would only
        re-404 the dead code). Returns False (logging why) if it ultimately fails,
        so the caller abandons the registration."""
        path = self._openbao_github_app_path(connection_id)
        body = {"data": {"app_id": str(app.get("id", "")), "private_key": app.get("pem", "")}}
        for attempt in range(3):
            resp = self._openbao_request("POST", path, body)
            if resp is not None and resp.ok:
                # A freshly-written key invalidates any cached miss for this connection.
                self._github_app_creds_cache.pop(connection_id, None)
                return True
            logger.error(
                f"❌ Could not write connection App key to OpenBao ({path}) "
                f"[attempt {attempt + 1}/3]: {resp.status_code if resp is not None else 'no response'}"
            )
            if attempt < 2:
                time.sleep(2)
        return False

    async def _abandon_registration(self, session, connection_id: str) -> None:
        """Tell teams-api to drop a registration the operator can't complete (dead
        code, or key store failed post-conversion), so it stops being re-served and
        the picker shows no stuck 'pending' connection. Best-effort."""
        try:
            async with session.delete(
                f"{self.teams_api_url}/internal/github-registrations/{connection_id}",
                headers=self._api_auth_headers(),
            ) as resp:
                if resp.status == 200:
                    logger.info(f"🗑️ Abandoned unrecoverable GitHub registration '{connection_id}'")
                else:
                    logger.error(f"Failed to abandon github-registration: HTTP {resp.status}")
        except aiohttp.ClientError as e:
            logger.error(f"Error abandoning github-registration: {e}")

    async def resolve_github_connections(self):
        """Resolve pending GitHub App connections teams-api recorded: for each
        {target, installation_id}, enumerate the installation's repos (App key)
        and report them back so teams-api adds them. Runs at the top of a reconcile
        so the freshly-added repos are included in this same cycle's fetch_teams.
        Best-effort: a failure leaves the pending row for next cycle."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.teams_api_url}/internal/github-connections",
                    headers=self._api_auth_headers(),
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to fetch pending github-connections: HTTP {resp.status}")
                        return
                    pending = await resp.json()

                for conn in pending:
                    target, installation_id = conn.get("target"), conn.get("installation_id")
                    connection_id = conn.get("connection_id") or None
                    if not target or not installation_id:
                        continue
                    repos = self._github_installation_repos(installation_id, connection_id)
                    if repos is None:
                        continue  # couldn't enumerate; leave pending for retry
                    async with session.post(
                        f"{self.teams_api_url}/internal/github-connections/resolve",
                        headers=self._api_auth_headers(),
                        json={
                            "target": target,
                            "installation_id": installation_id,
                            "connection_id": connection_id or "",
                            "repos": repos,
                        },
                    ) as rresp:
                        if rresp.status == 200:
                            logger.info(
                                f"✅ Resolved GitHub connection for '{target}' "
                                f"(installation {installation_id}, {len(repos)} repo(s))"
                            )
                        else:
                            logger.error(f"Failed to resolve github-connection: HTTP {rresp.status}")
        except aiohttp.ClientError as e:
            logger.error(f"Error resolving github-connections: {e}")
        except Exception as e:  # noqa: BLE001 - must not kill the reconcile loop
            logger.error(f"Unexpected error resolving github-connections: {e}")

    def _emit_project_event(self, team_id: str, reason: str, message: str, healthy: bool = True) -> None:
        """Emit an Event for a project-level (not namespace-level) reconcile
        action — Keycloak groups, the AppProject, or the argocd-rbac-cm
        policy block. Labelled with the project id (same EVENT_TEAM_LABEL as
        every other Event here) so it surfaces in the Teams portal's
        per-project activity feed (events_reader.py's cluster-wide label
        query) alongside this project's per-namespace events, even though
        there's no single owning namespace to attach it to. Stored in the
        argocd namespace, co-located with the AppProject it references —
        core/v1 Events require metadata.namespace == involvedObject.namespace
        (verified against the API), so this can't live in the operator's own
        namespace: that mismatch is a hard 422 ('does not match
        event.namespace'). Where it's stored doesn't affect the portal feed,
        which reads Events by label cluster-wide (events_reader.py)."""
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
            self.k8s_core_v1.create_namespaced_event(self.ARGOCD_NAMESPACE, body)
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

    # ------------------------------------------------------------------ #
    # Keycloak realm-write (gated by KC_RECONCILE_ENABLED — see __init__).
    # Admin client_secret comes from OpenBao (read via this pod's SPIFFE
    # identity), so there is no static Keycloak secret on the pod.
    # ------------------------------------------------------------------ #
    def _kc_client_secret(self) -> Optional[str]:
        resp = self._openbao_request("GET", self.kc_secret_openbao_path)
        if resp is None or resp.status_code != 200:
            code = getattr(resp, "status_code", "no response")
            logger.error(f"❌ Keycloak-admin secret unreadable from OpenBao "
                         f"({self.kc_secret_openbao_path}): {code}")
            return None
        try:
            return resp.json()["data"]["data"]["client-secret"]
        except (KeyError, ValueError) as e:
            logger.error(f"❌ Malformed Keycloak-admin secret at {self.kc_secret_openbao_path}: {e}")
            return None

    def _kc_token_get(self) -> Optional[str]:
        if self._kc_token and time.time() < self._kc_token_expiry - 15:
            return self._kc_token
        secret = self._kc_client_secret()
        if not secret:
            return None
        try:
            resp = requests.post(
                f"{self.kc_base_url}/realms/{self.kc_realm}/protocol/openid-connect/token",
                data={"grant_type": "client_credentials",
                      "client_id": self.kc_client_id, "client_secret": secret},
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.error(f"❌ Keycloak admin token failed (client_id={self.kc_client_id}): {e}")
            return None
        self._kc_token = body["access_token"]
        self._kc_token_expiry = time.time() + int(body.get("expires_in", 60))
        return self._kc_token

    def _kc_request(self, method: str, path: str, **kw) -> Optional[requests.Response]:
        token = self._kc_token_get()
        if not token:
            return None
        try:
            return requests.request(
                method, f"{self.kc_base_url}/admin/realms/{self.kc_realm}{path}",
                headers={"Authorization": f"Bearer {token}"}, timeout=10, **kw,
            )
        except requests.RequestException as e:
            logger.error(f"❌ Keycloak admin {method} {path} failed: {e}")
            return None

    def _kc_group_id(self, name: str) -> Optional[str]:
        if name in self._kc_group_ids:
            return self._kc_group_ids[name]
        resp = self._kc_request("GET", "/groups", params={"search": name, "max": 100})
        if resp is None or resp.status_code != 200:
            return None
        for g in resp.json():
            if g.get("name") == name:
                self._kc_group_ids[name] = g["id"]
                return g["id"]
        return None

    def _kc_ensure_group(self, name: str) -> Optional[str]:
        gid = self._kc_group_id(name)
        if gid:
            return gid
        # `managed-by` marks operator-owned groups so prune only ever touches ours.
        resp = self._kc_request("POST", "/groups",
                                json={"name": name, "attributes": {"managed-by": ["teams-operator"]}})
        if resp is None or resp.status_code not in (201, 409):
            logger.error(f"❌ create Keycloak group '{name}': {getattr(resp,'status_code','no response')}")
            return None
        return self._kc_group_id(name)

    def _kc_delete_group(self, name: str) -> bool:
        gid = self._kc_group_id(name)
        if not gid:
            return True
        resp = self._kc_request("DELETE", f"/groups/{gid}")
        ok = resp is not None and resp.status_code in (204, 404)
        if ok:
            self._kc_group_ids.pop(name, None)
        else:
            logger.error(f"❌ delete Keycloak group '{name}': {getattr(resp,'status_code','no response')}")
        return ok

    def _kc_group_members(self, name: str) -> Optional[List[str]]:
        gid = self._kc_group_id(name)
        if not gid:
            return []
        resp = self._kc_request("GET", f"/groups/{gid}/members", params={"max": 1000})
        if resp is None or resp.status_code != 200:
            return None
        return [u["username"] for u in resp.json()]

    def _kc_user_id(self, username: str) -> Optional[str]:
        resp = self._kc_request("GET", "/users", params={"username": username, "exact": "true"})
        if resp is None or resp.status_code != 200:
            return None
        users = resp.json()
        return users[0]["id"] if users else None

    def _kc_set_group_membership(self, name: str, username: str, add: bool) -> bool:
        gid = self._kc_ensure_group(name) if add else self._kc_group_id(name)
        if not gid:
            return not add  # removing from a group that doesn't exist: nothing to do
        uid = self._kc_user_id(username)
        if not uid:
            logger.warning(f"⚠️ Keycloak user '{username}' not found; skipping group '{name}'")
            return False
        resp = self._kc_request("PUT" if add else "DELETE", f"/users/{uid}/groups/{gid}")
        return resp is not None and resp.status_code in (204, 404)

    def _kc_role_repr(self, role: str) -> Optional[dict]:
        resp = self._kc_request("GET", f"/roles/{role}")
        if resp is None or resp.status_code != 200:
            return None
        r = resp.json()
        return {"id": r["id"], "name": r["name"]}

    def _kc_role_members(self, role: str) -> Optional[List[str]]:
        resp = self._kc_request("GET", f"/roles/{role}/users", params={"max": 1000})
        if resp is None or resp.status_code != 200:
            return None
        return [u["username"] for u in resp.json()]

    def _kc_set_realm_role(self, username: str, role: str, add: bool) -> bool:
        uid = self._kc_user_id(username)
        if not uid:
            logger.warning(f"⚠️ Keycloak user '{username}' not found; skipping role '{role}'")
            return False
        rep = self._kc_role_repr(role)
        if not rep:
            return False
        resp = self._kc_request("POST" if add else "DELETE",
                                f"/users/{uid}/role-mappings/realm", json=[rep])
        return resp is not None and resp.status_code in (204, 409)

    def reconcile_keycloak(self, access: dict) -> None:
        """SOLE Keycloak writer (when enabled): reconcile the k8s-access groups,
        project-owner groups, and the project-manager realm role to teams-api's
        desired state (/internal/access). Best-effort per item; a transient
        Keycloak failure just retries next cycle. Fully isolated so it can never
        stall the k8s/OpenBao/Argo reconcile."""
        try:
            namespaces = access.get("namespaces") or {}
            owner_groups = access.get("owner_groups") or {}
            project_managers = access.get("project_managers")  # None => not reported

            desired_groups: Dict[str, Set[str]] = {}
            for ns, roles in namespaces.items():
                desired_groups[f"{ns}-viewer"] = set(roles.get("viewer", []))
                desired_groups[f"{ns}-maintainer"] = set(roles.get("maintainer", []))
            for gname, members in owner_groups.items():
                desired_groups[gname] = set(members)

            # 1) Converge each desired group's membership.
            for gname, want in desired_groups.items():
                have = self._kc_group_members(gname)
                if have is None:
                    continue  # read failed this cycle; leave as-is, retry later
                have = set(have)
                for u in want - have:
                    self._kc_set_group_membership(gname, u, add=True)
                for u in have - want:
                    self._kc_set_group_membership(gname, u, add=False)

            # 2) Prune operator-managed groups no longer desired (only groups we
            #    created carry the managed-by attribute, so we never touch others).
            resp = self._kc_request("GET", "/groups",
                                    params={"max": 2000, "briefRepresentation": "false"})
            if resp is not None and resp.status_code == 200:
                for g in resp.json():
                    name = g.get("name", "")
                    ours = (g.get("attributes") or {}).get("managed-by") == ["teams-operator"]
                    if ours and name not in desired_groups:
                        self._kc_delete_group(name)

            # 3) project-manager realm role. None => teams-api didn't report it
            #    (mid-rollout) — leave it alone rather than revoke everyone.
            if project_managers is not None:
                have_pm = self._kc_role_members(self.kc_pm_role)
                if have_pm is not None:
                    want_pm, have_pm = set(project_managers), set(have_pm)
                    for u in want_pm - have_pm:
                        self._kc_set_realm_role(u, self.kc_pm_role, add=True)
                    for u in have_pm - want_pm:
                        self._kc_set_realm_role(u, self.kc_pm_role, add=False)
        except Exception as e:  # noqa: BLE001 — a Keycloak hiccup must not stall the cycle
            logger.error(f"❌ Keycloak reconcile cycle failed: {e}")

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

    def ensure_openbao_access(self, slug: str, namespace: str) -> bool:
        """Ensure `namespace` (of project `slug`) has everything both a tenant
        pod's openbao-agent sidecar AND a human logging in via OIDC SSO need to
        reach this namespace's slice of the layered kv mount: a maintainer
        (full CRUD) ACL policy scoped to this namespace's subtree plus the
        project's shared bucket (see project-maintainer.hcl — path layout in
        docs/self-service-repos-github-app.md), a jwt auth role mapping this
        namespace's SPIFFE IDs to that policy (workloads always get maintainer —
        they need to write their own secrets), and an identity group-alias
        mapping the "{namespace}-maintainer" Keycloak group (the same group
        already used for k8s RBAC and Argo CD's RBAC — see _rbac_policy_block)
        to it. Plus the agent-config ConfigMap the sidecars mount (see
        apps/security/tenant-guardrails's openbao-spiffe-volume-*.yaml).

        No OpenBao viewer policy/alias is created: ns viewers get no OpenBao
        access at all (the viewer Keycloak group still drives k8s/Argo RBAC).
        Project-WIDE owner access is a separate concern — see
        ensure_openbao_project_access, called once per project.

        Create-if-missing/leave-as-is-on-conflict, same semantics as
        _apply_namespaced_templates (the group-alias is the one exception, since
        OpenBao 400s on a re-create — see _ensure_openbao_group_alias). Returns
        True only if everything is confirmed OK this cycle — a partial success
        is exactly the broken-but-not-obvious state that motivated surfacing
        this as a per-namespace "OpenBaoAccess" condition, so it's reported as
        not-ready, not silently swallowed."""
        ok = True

        try:
            with open(os.path.join(self.OPENBAO_POLICY_TEMPLATES_DIR, "project-maintainer.hcl")) as f:
                maintainer_policy_hcl = (
                    f.read().replace("{{ SLUG }}", slug).replace("{{ NAMESPACE }}", namespace)
                )
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

    def ensure_openbao_project_access(self, slug: str) -> bool:
        """Ensure the PROJECT-wide owner tier for project `slug`: an ACL policy
        granting CRUD over the whole `kv/…/projects/<slug>/*` subtree (the
        project-management level, the shared bucket, and every namespace —
        present and future; see project-owner.hcl), plus an identity group-alias
        mapping the "project-<slug>-owner" Keycloak group to it. teams-api syncs
        the project's DB owners into that Keycloak group (the human side of the
        binding), the same way it syncs per-namespace maintainer membership.

        Distinct from ensure_openbao_access (per-namespace, maintainer-scoped):
        this runs once per project. Create-if-missing/idempotent; the alias is
        the usual re-create exception (see _ensure_openbao_group_alias)."""
        try:
            with open(os.path.join(self.OPENBAO_POLICY_TEMPLATES_DIR, "project-owner.hcl")) as f:
                owner_policy_hcl = f.read().replace("{{ SLUG }}", slug)
        except OSError as e:
            logger.error(f"❌ Could not read OpenBao project-owner policy template: {e}")
            return False

        ok = True
        policy_name = f"project-{slug}-owner-policy"
        resp = self._openbao_request(
            "PUT", f"sys/policies/acl/{policy_name}", {"policy": owner_policy_hcl}
        )
        if resp is not None and resp.ok:
            logger.info(f"✅ Ensured OpenBao policy '{policy_name}'")
        else:
            logger.error(
                f"❌ Failed to write OpenBao owner policy for project '{slug}': "
                f"HTTP {resp.status_code if resp is not None else 'no response'} {resp.text if resp is not None else ''}"
            )
            ok = False

        if not self._ensure_openbao_group_alias(f"project-{slug}-owner", policy_name):
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

    def delete_openbao_access(self, slug: str, namespace: str) -> bool:
        """Tear down everything ensure_openbao_access ever created for
        `namespace` (of project `slug`) when a single namespace is removed:
        every secret under kv/…/projects/<slug>/namespaces/<namespace>/*, the
        maintainer ACL policy, the workload jwt auth role, and the maintainer
        identity group (deleting a group also removes its group-alias - there's
        no separate alias cleanup call). The project-wide owner tier and the
        shared bucket are NOT touched here - they belong to the project, not
        this namespace, and are cleaned by delete_openbao_project_access on full
        project deletion. Best-effort like every other OpenBao call here: a
        transient failure is logged and reported, not raised, so it never blocks
        the k8s namespace deletion itself."""
        ok = self._delete_kv_tree(f"projects/{slug}/namespaces/{namespace}")

        resp = self._openbao_request("DELETE", f"auth/jwt/role/{namespace}")
        if resp is not None and (resp.ok or resp.status_code == 404):
            logger.info(f"✅ Deleted OpenBao jwt auth role '{namespace}'")
        else:
            logger.error(
                f"❌ Failed to delete OpenBao jwt auth role '{namespace}': "
                f"HTTP {resp.status_code if resp is not None else 'no response'} {resp.text if resp is not None else ''}"
            )
            ok = False

        resp = self._openbao_request("DELETE", f"sys/policies/acl/{namespace}-maintainer-policy")
        if resp is not None and (resp.ok or resp.status_code == 404):
            logger.info(f"✅ Deleted OpenBao policy '{namespace}-maintainer-policy'")
        else:
            logger.error(
                f"❌ Failed to delete OpenBao policy '{namespace}-maintainer-policy': "
                f"HTTP {resp.status_code if resp is not None else 'no response'} "
                f"{resp.text if resp is not None else ''}"
            )
            ok = False

        resp = self._openbao_request("DELETE", f"identity/group/name/{namespace}-maintainer")
        if resp is not None and (resp.ok or resp.status_code == 404):
            logger.info(f"✅ Deleted OpenBao identity group '{namespace}-maintainer'")
        else:
            logger.error(
                f"❌ Failed to delete OpenBao identity group '{namespace}-maintainer': "
                f"HTTP {resp.status_code if resp is not None else 'no response'} "
                f"{resp.text if resp is not None else ''}"
            )
            ok = False

        return ok

    def delete_openbao_project_access(self, slug: str) -> bool:
        """Tear down the whole project subtree in OpenBao on project deletion:
        every secret under kv/…/projects/<slug>/* (platform + shared + all
        namespaces), the project-wide owner ACL policy, and the owner identity
        group (its alias goes with it). Per-namespace teardown
        (delete_openbao_access) already removed each namespace's policy/role/
        group; this cleans the project-level objects and guarantees the KV tree
        is fully gone even if a namespace teardown was skipped. Best-effort."""
        ok = self._delete_kv_tree(f"projects/{slug}")

        resp = self._openbao_request("DELETE", f"sys/policies/acl/project-{slug}-owner-policy")
        if resp is not None and (resp.ok or resp.status_code == 404):
            logger.info(f"✅ Deleted OpenBao policy 'project-{slug}-owner-policy'")
        else:
            logger.error(
                f"❌ Failed to delete OpenBao policy 'project-{slug}-owner-policy': "
                f"HTTP {resp.status_code if resp is not None else 'no response'} "
                f"{resp.text if resp is not None else ''}"
            )
            ok = False

        resp = self._openbao_request("DELETE", f"identity/group/name/project-{slug}-owner")
        if resp is not None and (resp.ok or resp.status_code == 404):
            logger.info(f"✅ Deleted OpenBao identity group 'project-{slug}-owner'")
        else:
            logger.error(
                f"❌ Failed to delete OpenBao identity group 'project-{slug}-owner': "
                f"HTTP {resp.status_code if resp is not None else 'no response'} "
                f"{resp.text if resp is not None else ''}"
            )
            ok = False

        return ok

    def _emit_event(
        self, event_namespace: str, involved_namespace: str, team_id: Optional[str],
        reason: str, message: str, healthy: bool = True,
    ) -> None:
        """Emit a Kubernetes Event about the `involved_namespace` Namespace,
        read by the Teams portal (via teams-api's events_reader.py, a
        cluster-wide query by the team-id label) for a per-team activity feed.

        Core/v1 Events are validated so metadata.namespace ==
        involvedObject.namespace (and a cluster-scoped involvedObject — empty
        namespace — must be stored in `default`); both rules are enforced by
        the apiserver, verified live. Normally `event_namespace` equals
        `involved_namespace`, so the Event is co-located in that namespace and
        `kubectl get events -n <ns>` works naturally. When the caller passes a
        DIFFERENT `event_namespace` (delete_namespace does — the namespace is
        being torn down, and an Event stored inside it would be cascade-deleted
        before reaching the UI), the Namespace is referenced cluster-scoped (it
        IS a cluster-scoped object) and the Event stored in `default`, the only
        namespace the apiserver allows for a cluster-scoped involvedObject.
        Best-effort: a failure to emit must never break reconciliation, so this
        only logs on error. Shared low-level primitive for namespace lifecycle
        events (create_namespace/delete_namespace) and provisioning-condition
        transitions (update_namespace_status)."""
        now = datetime.now(timezone.utc)
        labels = {self.EVENT_TEAM_LABEL: team_id} if team_id else {}
        if event_namespace == involved_namespace:
            store_namespace = involved_namespace
            involved_object_namespace = involved_namespace
        else:
            # Can't co-locate (the namespace is going away): reference the
            # Namespace cluster-scoped and store the Event in `default`.
            store_namespace = "default"
            involved_object_namespace = None
        body = client.CoreV1Event(
            metadata=client.V1ObjectMeta(generate_name=f"teams-operator-{involved_namespace}-", labels=labels),
            involved_object=client.V1ObjectReference(
                kind="Namespace", name=involved_namespace, namespace=involved_object_namespace, api_version="v1"
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
            self.k8s_core_v1.create_namespaced_event(store_namespace, body)
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
        default`, but the Teams portal has no cluster-wide activity view
        today to show it in. Stored in `default`, not the operator's own
        namespace: a cluster-scoped involvedObject (empty namespace) forces
        the Event into `default` — anywhere else is a hard 422 (verified
        against the API)."""
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
            self.k8s_core_v1.create_namespaced_event("default", body)
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
        # The slug is tracked in _project_slugs (populated even for projects
        # whose DB record is already gone — that's its purpose). Without it we
        # can't build the layered kv path, so skip per-namespace OpenBao cleanup
        # and rely on delete_openbao_project_access to wipe the whole subtree.
        slug = self._project_slugs.get(team_id)
        if slug:
            openbao_ok = self.delete_openbao_access(slug, namespace_name)
        else:
            logger.warning(
                f"⚠️ No slug known for team '{team_id}'; skipping per-namespace OpenBao "
                f"cleanup of '{namespace_name}' (project-level teardown will cover it)"
            )
            openbao_ok = True
        try:
            self.k8s_core_v1.delete_namespace(name=namespace_name)
            logger.info(f"🗑️ Deleted namespace '{namespace_name}' for removed team '{team_name}'")
            # Pass a DIFFERENT event_namespace than namespace_name: that
            # namespace is being torn down right now, and an Event stored
            # inside it would be cascade-deleted before reaching the UI. This
            # signals _emit_event to reference the Namespace cluster-scoped and
            # store the Event in `default` instead. See _emit_event.
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
        # Convert any pending GitHub App-Manifest registrations first (so a
        # newly-registered connection is 'ready' with its key in OpenBao before
        # anything downstream needs it), then resolve pending repo connections, so
        # repos a user just connected are already present in this cycle's fetch_teams.
        await self.resolve_github_registrations()
        await self.resolve_github_connections()

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
            # Wipe the whole project subtree in OpenBao + the owner tier (the
            # per-namespace teardown ran in delete_namespace as each namespace
            # went away; this covers the project-level objects and any residue).
            openbao_ok = self.delete_openbao_project_access(slug)
            # The shared githubApp repo-creds are cluster-wide, not per project —
            # reconcile_github_repo_creds prunes any no longer referenced by any
            # remaining project, so nothing project-specific to delete here.
            if apps_ok and appproject_ok and rbac_ok and openbao_ok:
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
                # The layered kv path needs the project slug; take it from the
                # live team record (or the slug-tracking map as a fallback).
                slug = (current_teams.get(team_id) or {}).get("argocd_project") \
                    or self._project_slugs.get(team_id)
                if slug:
                    openbao_ok = self.ensure_openbao_access(slug, namespace_name)
                else:
                    logger.warning(
                        f"⚠️ No slug known for team '{team_id}'; skipping OpenBao access "
                        f"provisioning for '{namespace_name}' this cycle"
                    )
                    openbao_ok = False
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
            # source_repos is already the effective list (per-project repos
            # UNIONed with the admin global whitelist) — teams-api computes the
            # union in /internal/teams, so a change to the global whitelist
            # changes this tuple for every project and re-triggers the reconcile
            # below via state_key. No separate global fetch needed here.
            # source_repos already includes GitHub-connected repos (teams-api adds
            # them to the project's repos on resolve), so the existing state key
            # covers connect/disconnect. The App CREDENTIAL is materialized once,
            # cluster-wide, after this loop (reconcile_github_repo_creds) — a
            # single repo-creds per account, not per project.
            source_repos = tuple(sorted(team.get('source_repos') or []))
            state_key = (frozenset(namespaces), source_repos)
            if self._last_project_state.get(team_id) == state_key:
                continue  # nothing this operator manages has changed

            appproject_ok = self.ensure_argocd_appproject(argocd_project, namespaces, list(source_repos))
            rbac_ok = self.ensure_argocd_rbac_policy(argocd_project, namespaces)
            # Project-wide OpenBao owner tier (once per project — distinct from
            # the per-namespace maintainer access in the RBAC-part-1 loop above).
            openbao_proj_ok = self.ensure_openbao_project_access(argocd_project)

            if appproject_ok and rbac_ok and openbao_proj_ok:
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
                    f"(appproject={appproject_ok}, rbac={rbac_ok}, openbao={openbao_proj_ok})",
                    healthy=False,
                )

        # Cluster-wide GitHub App repo credentials. Two complementary paths:
        #  - platform-App (connection-less) repos + the global whitelist: one
        #    account-level repo-creds template each (reconcile_github_repo_creds).
        #  - per-project-connection repos: one exact-URL repository secret each
        #    (ensure_connection_repo_credentials), so multiple connections over the
        #    same GitHub account don't collide on a shared prefix.
        self.reconcile_github_repo_creds(current_teams)
        self.ensure_connection_repo_credentials(current_teams)

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

        # Keycloak realm-write reconcile (k8s-access groups, project-owner groups,
        # project-manager role). GATED OFF until cutover (KC_RECONCILE_ENABLED);
        # teams-api still owns these writes until then. Reuses this cycle's
        # already-fetched `access`, so it costs no extra teams-api call.
        if self.kc_reconcile_enabled:
            self.reconcile_keycloak(access)

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
