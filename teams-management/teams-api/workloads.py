"""
Applications reader for the Teams API.

Lists the applications running in each team's Kubernetes namespace and reports
their name + version, so the portal can show what a team is running on its card.

An "application" is an Argo Rollout or a Deployment in the team namespace. For
each we derive:
  * name    - the `app.kubernetes.io/name` label, else the workload's own name.
  * version - the `app.kubernetes.io/version` label, else the image tag of the
              first container.

Team -> namespace is resolved via the label the teams-operator stamps
(`teams.example.com/team-id`), the same approach used by the compliance checker.
"""

import logging
import threading
import time
from typing import Dict, List, Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger("teams-api.workloads")

TEAM_ID_LABEL = "teams.example.com/team-id"
NAME_LABEL = "app.kubernetes.io/name"
VERSION_LABEL = "app.kubernetes.io/version"
PART_OF_LABEL = "app.kubernetes.io/part-of"

ROLLOUT_GROUP = "argoproj.io"
ROLLOUT_VERSION = "v1alpha1"
ROLLOUT_PLURAL = "rollouts"

# Label Argo Rollouts stamps on each managed ReplicaSet, used to map the
# blue/green active/preview selectors back to a concrete image version.
ROLLOUT_HASH_LABEL = "rollouts-pod-template-hash"

# Per-namespace workload listing is reused for this long before refreshing.
CACHE_TTL_SECONDS = 15


class ApplicationsReader:
    """Reads the applications (Rollouts + Deployments) in each team namespace."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache: Dict[str, dict] = {}  # namespace -> {"apps": [...], "at": ts}
        self._k8s_ready = False

        try:
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except config.ConfigException:
                config.load_kube_config()
                logger.info("Loaded local kubeconfig")
            self._core = client.CoreV1Api()
            self._apps = client.AppsV1Api()
            self._custom = client.CustomObjectsApi()
            self._k8s_ready = True
        except Exception as e:  # noqa: BLE001 - degrade gracefully, never crash the API
            logger.error(f"Kubernetes client unavailable, applications will be empty: {e}")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def applications_for_all(self, teams: List[dict]) -> List[dict]:
        """Return the application list for every team."""
        namespaces = self._team_namespaces()
        return [self._for_team(team, namespaces.get(team["id"])) for team in teams]

    def applications_for_team(self, team: dict) -> dict:
        """Return the application list for a single team."""
        namespace = self._team_namespaces().get(team["id"])
        return self._for_team(team, namespace)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _for_team(self, team: dict, namespace: Optional[str]) -> dict:
        return {
            "team_id": team["id"],
            "team_name": team["name"],
            "namespace": namespace,
            "applications": self._apps_in_namespace(namespace) if namespace else [],
        }

    def _apps_in_namespace(self, namespace: str) -> List[dict]:
        if not self._k8s_ready:
            return []

        with self._lock:
            cached = self._cache.get(namespace)
            if cached is not None and (time.time() - cached["at"]) < CACHE_TTL_SECONDS:
                return cached["apps"]

        apps: List[dict] = []
        rs_versions = self._replicaset_versions(namespace)
        apps.extend(self._rollouts(namespace, rs_versions))
        apps.extend(self._deployments(namespace))
        apps.sort(key=lambda a: a["name"])

        with self._lock:
            self._cache[namespace] = {"apps": apps, "at": time.time()}
        return apps

    def _rollouts(self, namespace: str, rs_versions: Dict[str, Dict[str, str]]) -> List[dict]:
        try:
            objs = self._custom.list_namespaced_custom_object(
                ROLLOUT_GROUP, ROLLOUT_VERSION, namespace, ROLLOUT_PLURAL
            )
        except ApiException as e:
            if e.status != 404:  # 404 => Argo Rollouts CRD not installed; just skip
                logger.warning(f"Could not list rollouts in {namespace}: {e.status}")
            return []
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Unexpected error listing rollouts in {namespace}: {e}")
            return []

        apps = []
        for obj in objs.get("items", []):
            meta = obj.get("metadata", {}) or {}
            spec = obj.get("spec", {}) or {}
            status = obj.get("status", {}) or {}
            containers = (spec.get("template", {}).get("spec", {}) or {}).get("containers", [])
            image = containers[0].get("image", "") if containers else ""
            name = meta.get("name", "")

            app = self._to_app(
                name=name,
                labels=meta.get("labels", {}),
                image=image,
                kind="Rollout",
                replicas=spec.get("replicas"),
                ready=status.get("readyReplicas"),
            )
            app["rollout"] = self._rollout_status(spec, status, rs_versions.get(name, {}))
            # For a blue/green rollout the live version is the active one, which
            # differs from the spec image while a promotion is pending.
            if app["rollout"] and app["rollout"].get("active_version"):
                app["version"] = app["rollout"]["active_version"]
            apps.append(app)
        return apps

    def _rollout_status(self, spec: dict, status: dict, versions: Dict[str, str]) -> Optional[dict]:
        """Blue/green (or canary) status for a Rollout, keyed off its ReplicaSets."""
        strategy = spec.get("strategy", {}) or {}
        if "blueGreen" in strategy:
            strategy_type = "BlueGreen"
        elif "canary" in strategy:
            strategy_type = "Canary"
        else:
            strategy_type = "Unknown"

        bg = status.get("blueGreen", {}) or {}
        active_sel = bg.get("activeSelector")
        preview_sel = bg.get("previewSelector")
        active_version = versions.get(active_sel) if active_sel else None
        preview_version = (
            versions.get(preview_sel)
            if preview_sel and preview_sel != active_sel
            else None
        )

        pause_conditions = status.get("pauseConditions") or []
        awaiting_promotion = any(
            pc.get("reason") == "BlueGreenPause" for pc in pause_conditions
        )

        return {
            "strategy": strategy_type,
            "phase": status.get("phase", "Unknown"),
            "message": status.get("message", ""),
            "active_version": active_version,
            "preview_version": preview_version,
            "awaiting_promotion": awaiting_promotion,
        }

    def _replicaset_versions(self, namespace: str) -> Dict[str, Dict[str, str]]:
        """Map rollout name -> {pod-template-hash -> version} for its ReplicaSets."""
        result: Dict[str, Dict[str, str]] = {}
        try:
            rs_list = self._apps.list_namespaced_replica_set(namespace)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not list replicasets in {namespace}: {e}")
            return result

        for rs in rs_list.items:
            owners = rs.metadata.owner_references or []
            rollout = next((o.name for o in owners if o.kind == "Rollout"), None)
            labels = rs.metadata.labels or {}
            pod_hash = labels.get(ROLLOUT_HASH_LABEL)
            if not rollout or not pod_hash:
                continue
            tmpl_labels = (rs.spec.template.metadata.labels or {}) if rs.spec.template else {}
            containers = rs.spec.template.spec.containers if rs.spec.template else []
            image = containers[0].image if containers else ""
            version = _resolve_version(image, tmpl_labels.get(VERSION_LABEL))
            result.setdefault(rollout, {})[pod_hash] = version
        return result

    def _deployments(self, namespace: str) -> List[dict]:
        try:
            deps = self._apps.list_namespaced_deployment(namespace)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not list deployments in {namespace}: {e}")
            return []

        apps = []
        for dep in deps.items:
            labels = dep.metadata.labels or {}
            containers = dep.spec.template.spec.containers
            image = containers[0].image if containers else ""
            apps.append(self._to_app(
                name=dep.metadata.name,
                labels=labels,
                image=image,
                kind="Deployment",
                replicas=dep.spec.replicas,
                ready=dep.status.ready_replicas,
            ))
        return apps

    def _to_app(self, name, labels, image, kind, replicas, ready) -> dict:
        labels = labels or {}
        return {
            "name": labels.get(NAME_LABEL) or name,
            "version": _resolve_version(image, labels.get(VERSION_LABEL)),
            "kind": kind,
            "image": image,
            "replicas": replicas or 0,
            "ready_replicas": ready or 0,
            "part_of": labels.get(PART_OF_LABEL),
            "rollout": None,  # populated for Rollout kind by _rollouts()
        }

    def _team_namespaces(self) -> Dict[str, str]:
        """Map team_id -> namespace using the label the operator stamps."""
        if not self._k8s_ready:
            return {}
        try:
            ns_list = self._core.list_namespace(label_selector=TEAM_ID_LABEL)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to list team namespaces: {e}")
            return {}

        mapping: Dict[str, str] = {}
        for ns in ns_list.items:
            labels = ns.metadata.labels or {}
            team_id = labels.get(TEAM_ID_LABEL)
            if team_id:
                mapping[team_id] = ns.metadata.name
        return mapping


def _image_tag(image: str) -> str:
    """Extract the version/tag from a container image reference."""
    if not image:
        return "unknown"
    # Drop any digest, then take the tag after the last ':' that isn't a port.
    ref = image.split("@", 1)[0]
    last = ref.rsplit("/", 1)[-1]  # registry:port/... is fine; only look at the final segment
    if ":" in last:
        return last.rsplit(":", 1)[1]
    return "latest"


def _resolve_version(image: str, label: Optional[str]) -> str:
    """Prefer the explicit image tag (source of truth after `set image`), then the
    app.kubernetes.io/version label, then the tagless fallback."""
    tag = _image_tag(image)
    if tag not in ("latest", "unknown"):
        return tag
    return label or tag
