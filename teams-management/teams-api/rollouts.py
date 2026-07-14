"""
Blue/green rollout actions for the Teams API.

Exposes two operations the portal drives against a team's Argo Rollouts:
  * promote(team, app)          - promote the preview (green) to active (blue).
  * set_image(team, app, tag)   - deploy a new version by changing the image tag,
                                  which starts a new green/preview.

Actions shell out to the official `kubectl-argo-rollouts` plugin (bundled in the
image) rather than re-implementing its promotion patch logic. Everything is
passed as an argument list (never a shell string), and the namespace, rollout
name and image are all validated/derived server-side from the team's own
resources, so a caller cannot target arbitrary namespaces/images or inject args.
"""

import logging
import re
import subprocess
from typing import Optional, Tuple

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger("teams-api.rollouts")

PLUGIN = "kubectl-argo-rollouts"
TEAM_ID_LABEL = "teams.example.com/team-id"
ROLLOUT_GROUP = "argoproj.io"
ROLLOUT_VERSION = "v1alpha1"
ROLLOUT_PLURAL = "rollouts"
ACTION_TIMEOUT_SECONDS = 30

# Docker image tags: a component may not start with a separator and is limited
# to [A-Za-z0-9._-], max 128 chars.
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ActionError(Exception):
    """Raised when an action fails validation or execution (maps to HTTP 4xx/5xx)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class RolloutActions:
    def __init__(self):
        self._k8s_ready = False
        try:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            self._core = client.CoreV1Api()
            self._apps = client.AppsV1Api()
            self._custom = client.CustomObjectsApi()
            self._k8s_ready = True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Kubernetes client unavailable, rollout actions disabled: {e}")

    # ------------------------------------------------------------------ #
    # Public actions
    # ------------------------------------------------------------------ #

    def promote(self, team: dict, app_name: str) -> dict:
        namespace, _ = self._resolve(team, app_name)
        out = self._run([PLUGIN, "promote", app_name, "-n", namespace])
        return {"action": "promote", "app": app_name, "namespace": namespace, "message": out}

    def set_image(self, team: dict, app_name: str, tag: str) -> dict:
        if not TAG_RE.match(tag or ""):
            raise ActionError(f"Invalid image tag: {tag!r}", status=400)
        namespace, rollout = self._resolve(team, app_name)

        container, current_image = self._container_image(rollout)
        repo, _ = _split_image(current_image)
        new_image = f"{repo}:{tag}"

        out = self._run([
            PLUGIN, "set", "image", app_name,
            f"{container}={new_image}", "-n", namespace,
        ])
        return {"action": "set_image", "app": app_name, "namespace": namespace,
                "image": new_image, "message": out}

    def discard_preview(self, team: dict, app_name: str) -> dict:
        """Discard a pending preview (green) by reverting the image to the active
        (blue) version. Leaves the rollout Healthy with no preview — unlike a raw
        abort, which leaves it Degraded."""
        namespace, rollout = self._resolve(team, app_name)

        active_image = self._active_image(namespace, rollout)
        if not active_image:
            raise ActionError("No active version to revert to (nothing to discard)", status=409)

        container, _ = self._container_image(rollout)
        out = self._run([
            PLUGIN, "set", "image", app_name,
            f"{container}={active_image}", "-n", namespace,
        ])
        return {"action": "discard", "app": app_name, "namespace": namespace,
                "image": active_image, "message": out}

    # ------------------------------------------------------------------ #
    # Validation / lookup
    # ------------------------------------------------------------------ #

    def _resolve(self, team: dict, app_name: str) -> Tuple[str, dict]:
        """Return (namespace, rollout object) after checking the app belongs to the team."""
        if not self._k8s_ready:
            raise ActionError("Kubernetes client unavailable", status=503)

        namespace = self._team_namespace(team["id"])
        if not namespace:
            raise ActionError("Team namespace not found", status=404)

        try:
            rollout = self._custom.get_namespaced_custom_object(
                ROLLOUT_GROUP, ROLLOUT_VERSION, namespace, ROLLOUT_PLURAL, app_name
            )
        except ApiException as e:
            if e.status == 404:
                raise ActionError(f"Rollout {app_name!r} not found in {namespace}", status=404)
            raise ActionError(f"Kubernetes API error ({e.status})", status=502)
        return namespace, rollout

    def _team_namespace(self, team_id: str) -> Optional[str]:
        try:
            ns_list = self._core.list_namespace(
                label_selector=f"{TEAM_ID_LABEL}={team_id}"
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to resolve namespace for team {team_id}: {e}")
            return None
        return ns_list.items[0].metadata.name if ns_list.items else None

    def _active_image(self, namespace: str, rollout: dict) -> Optional[str]:
        """The full image reference of the rollout's active (blue) ReplicaSet."""
        status = rollout.get("status", {}) or {}
        active_hash = (status.get("blueGreen", {}) or {}).get("activeSelector")
        if not active_hash:
            return None
        try:
            rs_list = self._apps.list_namespaced_replica_set(
                namespace, label_selector=f"rollouts-pod-template-hash={active_hash}"
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to list replicasets in {namespace}: {e}")
            return None
        for rs in rs_list.items:
            containers = rs.spec.template.spec.containers if rs.spec.template else []
            if containers:
                return containers[0].image
        return None

    def _container_image(self, rollout: dict) -> Tuple[str, str]:
        containers = (
            rollout.get("spec", {}).get("template", {}).get("spec", {}) or {}
        ).get("containers", [])
        if not containers:
            raise ActionError("Rollout has no containers", status=500)
        return containers[0].get("name", ""), containers[0].get("image", "")

    # ------------------------------------------------------------------ #
    # Plugin execution
    # ------------------------------------------------------------------ #

    def _run(self, args: list) -> str:
        logger.info(f"Running rollout action: {' '.join(args)}")
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, timeout=ACTION_TIMEOUT_SECONDS
            )
        except FileNotFoundError:
            raise ActionError(f"{PLUGIN} not found in image", status=500)
        except subprocess.TimeoutExpired:
            raise ActionError("Rollout action timed out", status=504)

        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "unknown error").strip()
            logger.error(f"Rollout action failed: {msg}")
            raise ActionError(f"Rollout action failed: {msg}", status=500)
        return (proc.stdout or "").strip()


def _split_image(image: str) -> Tuple[str, Optional[str]]:
    """Split an image reference into (repo, tag), preserving a registry:port host."""
    ref = image.split("@", 1)[0]
    if "/" in ref:
        prefix, last = ref.rsplit("/", 1)
        if ":" in last:
            name, tag = last.rsplit(":", 1)
            return f"{prefix}/{name}", tag
        return ref, None
    if ":" in ref:
        name, tag = ref.rsplit(":", 1)
        return name, tag
    return ref, None
