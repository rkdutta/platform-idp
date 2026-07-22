#!/usr/bin/env python3
"""
Teams Operator - Creates Kubernetes namespaces when teams are created in the Teams API
"""

import asyncio
import json
import logging
import os
import time
from typing import Set, Dict, Any
import aiohttp
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

        # Cluster-wide RBAC subjects mirror teams-api's permission model onto real
        # k8s RoleBindings (per-namespace) + one ClusterRoleBinding (admins) — see
        # sync_namespace_rbac / sync_admin_binding.
        self.RBAC_MANAGED_BY = {"app.kubernetes.io/managed-by": "teams-operator"}
        self.VIEWER_BINDING = "teams-sync-viewer"
        self.MAINTAINER_BINDING = "teams-sync-maintainer"
        self.ADMIN_BINDING = "teams-admins"


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

    def sync_namespace_rbac(self, namespace: str, viewers, maintainers) -> None:
        """Reconcile the two RoleBindings that give viewer/maintainer grants
        real effect in `namespace`, replacing the full subject list each call
        (cheap, and needs no extra operator-side state to diff against)."""
        for binding_name, role_name, usernames in (
            (self.VIEWER_BINDING, "view", viewers),
            (self.MAINTAINER_BINDING, "edit", maintainers),
        ):
            self._sync_role_binding(namespace, binding_name, role_name, usernames)

    def _sync_role_binding(self, namespace: str, name: str, cluster_role: str, usernames) -> None:
        subjects = [
            client.V1Subject(kind="User", name=u, api_group="rbac.authorization.k8s.io")
            for u in usernames
        ]
        body = client.V1RoleBinding(
            metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=self.RBAC_MANAGED_BY),
            role_ref=client.V1RoleRef(
                api_group="rbac.authorization.k8s.io", kind="ClusterRole", name=cluster_role
            ),
            subjects=subjects,
        )
        try:
            self.k8s_rbac_v1.create_namespaced_role_binding(namespace, body)
            logger.info(f"✅ Created RoleBinding '{name}' in '{namespace}' ({len(subjects)} subject(s))")
        except ApiException as e:
            if e.status == 409:  # already exists — replace the subject list
                try:
                    self.k8s_rbac_v1.patch_namespaced_role_binding(
                        name, namespace, {"subjects": [s.to_dict() for s in subjects]}
                    )
                except ApiException as patch_err:
                    logger.error(f"❌ Failed to update RoleBinding '{name}' in '{namespace}': {patch_err}")
            else:
                logger.error(f"❌ Failed to create RoleBinding '{name}' in '{namespace}': {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error syncing RoleBinding '{name}' in '{namespace}': {e}")

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

        # RBAC sync: mirror teams-api's permission model onto real RoleBindings
        # for every namespace we currently manage, plus the cluster-wide admin
        # binding. A namespace just deleted above is skipped here too — no
        # RoleBindings to sync for a namespace that no longer exists, and its
        # old ones went with it (namespace-scoped, cascade-deleted).
        access = await self.fetch_access()
        if access is None:
            logger.warning("Skipping RBAC sync: access could not be fetched from the API")
            return

        namespace_access = access.get("namespaces") or {}
        for provisioned in self.team_namespaces.values():
            for namespace_name in provisioned:
                grants = namespace_access.get(namespace_name, {"viewer": [], "maintainer": []})
                self.sync_namespace_rbac(
                    namespace_name, grants.get("viewer", []), grants.get("maintainer", [])
                )

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
