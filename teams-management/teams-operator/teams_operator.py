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
from typing import Set, Dict, Any
import aiohttp
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


    async def fetch_teams(self):
        """Fetch current teams from the Teams API.

        Uses the unauthenticated /internal/teams endpoint: teams-api enforces
        Keycloak JWT auth on the user-facing /teams (401 without a token), but the
        operator is an unscoped in-cluster controller with no user token. The
        internal endpoint returns just id/name/namespaces for reconciliation.

        Returns the list of teams on success, or None if the API could not be
        reached / returned an error. None is deliberately distinct from an empty
        list: an empty list means "no teams exist" (prune namespaces), whereas
        None means "unknown" and reconciliation must be skipped — otherwise a
        transient API outage (e.g. during a teams-api rollout) would be read as
        "all teams deleted" and wipe every team namespace.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.teams_api_url}/internal/teams") as response:
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
        """Fetch the current permission state from /internal/access:
        `{"namespaces": {ns: {"viewer": [...], "maintainer": [...]}},
        "admins": [...] | None}`.

        Returns None (not the dict) if the API was unreachable/errored, same
        "skip this cycle" contract as fetch_teams — an RBAC sync built on a
        failed fetch would either leave stale access in place or, worse,
        reconcile every namespace's RoleBindings down to empty subjects.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.teams_api_url}/internal/access") as response:
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

    def sync_namespace_rbac(self, namespace: str) -> None:
        """Ensure the two static RoleBindings exist that give k8s RBAC real
        effect in `namespace`, bound to Group subjects named deterministically
        from the namespace ("{namespace}-viewer" / "{namespace}-maintainer" —
        must match teams-api's _k8s_group_name). *Membership* in those groups
        (who's actually a viewer/maintainer right now) is synced straight into
        Keycloak by teams-api itself, not here — these bindings never change
        once created, so this is create-if-missing, no per-cycle patch."""
        for binding_name, cluster_role, role_tier in (
            (self.VIEWER_BINDING, "view", "viewer"),
            (self.MAINTAINER_BINDING, "edit", "maintainer"),
        ):
            self._ensure_group_role_binding(namespace, binding_name, cluster_role, role_tier)

    def _ensure_group_role_binding(
        self, namespace: str, name: str, cluster_role: str, role_tier: str
    ) -> None:
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
        except ApiException as e:
            if e.status == 409:
                pass  # already exists, subjects never change — nothing to reconcile
            else:
                logger.error(f"❌ Failed to create RoleBinding '{name}' in '{namespace}': {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error creating RoleBinding '{name}' in '{namespace}': {e}")

    def sync_admin_binding(self, usernames) -> None:
        """Reconcile the single cluster-wide ClusterRoleBinding that gives
        Keycloak `admin`-role holders real cluster-admin. Caller is
        responsible for not calling this when the admin list is unknown
        (None) — see reconcile_teams."""
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
        except ApiException as e:
            if e.status == 409:
                try:
                    self.k8s_rbac_v1.patch_cluster_role_binding(
                        self.ADMIN_BINDING, {"subjects": [s.to_dict() for s in subjects]}
                    )
                except ApiException as patch_err:
                    logger.error(f"❌ Failed to update ClusterRoleBinding '{self.ADMIN_BINDING}': {patch_err}")
            else:
                logger.error(f"❌ Failed to create ClusterRoleBinding '{self.ADMIN_BINDING}': {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error syncing ClusterRoleBinding '{self.ADMIN_BINDING}': {e}")

    def ensure_harbor_pull_secret(self, namespace: str) -> None:
        """Ensure `namespace` has the harbor-pull imagePullSecret, so
        workloads deployed there can pull from Harbor's private `platform`
        project — without this, every tenant workload 403s on image pull the
        same way engineering-platform's own components would without it.
        Create-if-missing only: like the RoleBindings, this is never patched
        again once it exists, so a manual credential rotation (new Secret
        content + operator redeploy) can't be silently overwritten by a
        stale in-memory value from a long-running pod."""
        if not self.harbor_dockerconfigjson:
            return
        body = client.V1Secret(
            metadata=client.V1ObjectMeta(name=self.HARBOR_PULL_SECRET, namespace=namespace),
            type="kubernetes.io/dockerconfigjson",
            string_data={".dockerconfigjson": self.harbor_dockerconfigjson},
        )
        try:
            self.k8s_core_v1.create_namespaced_secret(namespace, body)
            logger.info(f"✅ Created imagePullSecret '{self.HARBOR_PULL_SECRET}' in '{namespace}'")
        except ApiException as e:
            if e.status == 409:
                pass  # already exists
            else:
                logger.error(f"❌ Failed to create imagePullSecret in '{namespace}': {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error creating imagePullSecret in '{namespace}': {e}")

    def ensure_default_sa_pull_secret(self, namespace: str) -> None:
        """Attach harbor-pull to the namespace's default ServiceAccount, so
        every pod using it (the common case — app manifests owned by their
        own repos don't declare imagePullSecrets themselves) picks it up
        with no per-workload change needed."""
        if not self.harbor_dockerconfigjson:
            return
        try:
            sa = self.k8s_core_v1.read_namespaced_service_account("default", namespace)
        except ApiException as e:
            if e.status != 404:
                logger.error(f"❌ Could not read default ServiceAccount in '{namespace}': {e}")
            return
        except Exception as e:
            logger.error(f"❌ Unexpected error reading default ServiceAccount in '{namespace}': {e}")
            return

        existing = sa.image_pull_secrets or []
        if any(ref.name == self.HARBOR_PULL_SECRET for ref in existing):
            return  # already attached

        try:
            self.k8s_core_v1.patch_namespaced_service_account(
                "default",
                namespace,
                {"imagePullSecrets": [ref.to_dict() for ref in existing] + [{"name": self.HARBOR_PULL_SECRET}]},
            )
            logger.info(f"✅ Attached imagePullSecret '{self.HARBOR_PULL_SECRET}' to default SA in '{namespace}'")
        except ApiException as e:
            logger.error(f"❌ Failed to patch default ServiceAccount in '{namespace}': {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error patching default ServiceAccount in '{namespace}': {e}")

    def _apply_namespaced_templates(self, namespace: str, templates_dir: str, create_fn) -> None:
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
        very next reconciliation cycle, no restart required."""
        template_paths = sorted(glob.glob(os.path.join(templates_dir, "*.yaml")))
        if not template_paths:
            logger.warning(f"No templates found in {templates_dir}; skipping")
            return

        for path in template_paths:
            with open(path) as f:
                rendered = f.read().replace("{{ NAMESPACE }}", namespace)
            try:
                body = yaml.safe_load(rendered)
            except yaml.YAMLError as e:
                logger.error(f"❌ Template {path} is not valid YAML after rendering: {e}")
                continue
            kind = body.get("kind", "resource")
            name = body.get("metadata", {}).get("name", os.path.basename(path))
            try:
                create_fn(namespace, body)
                logger.info(f"✅ Created {kind} '{name}' in '{namespace}' (from {os.path.basename(path)})")
            except ApiException as e:
                if e.status == 409:
                    pass  # already exists
                else:
                    logger.error(f"❌ Failed to create {kind} '{name}' in '{namespace}': {e}")
            except Exception as e:
                logger.error(f"❌ Unexpected error creating {kind} '{name}' in '{namespace}': {e}")

    def ensure_priority_quotas(self, namespace: str) -> None:
        """Ensure `namespace` has one PriorityClass-scoped ResourceQuota per
        tenant tier (tenant-critical/-standard/-besteffort), so best-effort
        workloads can never starve a team's must-run ones of quota. The
        manifests themselves live as templates on disk (QUOTA_TEMPLATES_DIR
        — see the class-level comment), not as Python objects."""
        self._apply_namespaced_templates(
            namespace, self.QUOTA_TEMPLATES_DIR, self.k8s_core_v1.create_namespaced_resource_quota
        )

    def ensure_limit_ranges(self, namespace: str) -> None:
        """Ensure `namespace` has the default tenant LimitRange, so a
        container that doesn't declare its own requests/limits gets a sane
        default instead of running unbounded or with nothing at all. Same
        template-on-disk approach as ensure_priority_quotas — see
        LIMITRANGE_TEMPLATES_DIR."""
        self._apply_namespaced_templates(
            namespace, self.LIMITRANGE_TEMPLATES_DIR, self.k8s_core_v1.create_namespaced_limit_range
        )

    def ensure_network_policies(self, namespace: str) -> None:
        """Ensure `namespace` has the default tenant NetworkPolicy (deny all
        ingress, explicitly allow all egress — see
        networkpolicy-templates/default.yaml for why egress needs an
        explicit rule rather than just being left ungoverned). Same
        template-on-disk approach as ensure_priority_quotas — see
        NETWORKPOLICY_TEMPLATES_DIR."""
        self._apply_namespaced_templates(
            namespace, self.NETWORKPOLICY_TEMPLATES_DIR, self.k8s_networking_v1.create_namespaced_network_policy
        )

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
    
    def delete_namespace(self, namespace_name: str, team_name: str) -> bool:
        """Delete a Kubernetes namespace when team is removed"""
        try:
            self.k8s_core_v1.delete_namespace(name=namespace_name)
            logger.info(f"🗑️ Deleted namespace '{namespace_name}' for removed team '{team_name}'")
            return True
        except ApiException as e:
            if e.status == 404:  # Namespace doesn't exist
                logger.warning(f"⚠️ Namespace '{namespace_name}' not found (already deleted?)")
                return True
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
                if self.delete_namespace(namespace_name, team_name):
                    provisioned.discard(namespace_name)
                    changed = True

        # Handle deleted teams (remove all of their namespaces).
        deleted_teams = set(self.team_namespaces) - current_team_ids
        for team_id in deleted_teams:
            team_name = f"team-{team_id}"  # fallback; the team record is gone
            for namespace_name in list(self.team_namespaces[team_id]):
                if self.delete_namespace(namespace_name, team_name):
                    self.team_namespaces[team_id].discard(namespace_name)
            if not self.team_namespaces[team_id]:
                del self.team_namespaces[team_id]
                changed = True

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
        for provisioned in self.team_namespaces.values():
            for namespace_name in provisioned:
                self.sync_namespace_rbac(namespace_name)
                self.ensure_harbor_pull_secret(namespace_name)
                self.ensure_default_sa_pull_secret(namespace_name)
                self.ensure_priority_quotas(namespace_name)
                self.ensure_limit_ranges(namespace_name)
                self.ensure_network_policies(namespace_name)

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
