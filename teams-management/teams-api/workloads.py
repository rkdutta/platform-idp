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
import os
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
# Classifies an app so the portal can offer the right link: a "web" card links
# to the page, an "api" card links to its Swagger/OpenAPI docs.
COMPONENT_LABEL = "app.kubernetes.io/component"
# Where an API serves its docs (overrides the /docs default), and where a web
# app's landing page lives (overrides the / default).
DOCS_PATH_ANNOTATION = "platform.example.com/docs-path"
URL_PATH_ANNOTATION = "platform.example.com/url-path"
# "owner/repo" this workload's image is built from, so the portal can link a
# deployed version to its GitHub release. Only needed when the image name
# doesn't match the repo name (e.g. the engineering-platform components,
# which all build from the platform-idp monorepo) - otherwise it's derived
# from the image itself.
SOURCE_REPO_ANNOTATION = "platform.example.com/source-repo"
# Owner used when SOURCE_REPO_ANNOTATION gives a bare repo name (no "/"), and
# when deriving a repo from the image name.
GITHUB_ORG = os.getenv("GITHUB_ORG", "rkdutta")

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

        # Browser-facing ingress scheme/port, used to turn an Ingress host into a
        # clickable URL. Defaults match the kind platform (nginx on :8080).
        self._ingress_scheme = os.getenv("PUBLIC_INGRESS_SCHEME", "http")
        self._ingress_port = os.getenv("PUBLIC_INGRESS_PORT", "8080")

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
            self._net = client.NetworkingV1Api()
            self._k8s_ready = True
        except Exception as e:  # noqa: BLE001 - degrade gracefully, never crash the API
            logger.error(f"Kubernetes client unavailable, applications will be empty: {e}")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def applications_for_all(self, teams: List[dict]) -> List[dict]:
        """Return the application list for every team, across its namespaces.

        Each `team` dict carries `namespaces` (already narrowed by the caller to
        the namespaces the requester is allowed to see)."""
        return [self._for_team(team, team.get("namespaces") or []) for team in teams]

    def applications_for_team(self, team: dict) -> dict:
        """Return the application list for a single team, across its namespaces."""
        return self._for_team(team, team.get("namespaces") or [])

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _for_team(self, team: dict, namespaces: List[str]) -> dict:
        apps: List[dict] = []
        for ns in namespaces:
            for app in self._apps_in_namespace(ns):
                app["namespace"] = ns
                apps.append(app)
        return {
            "team_id": team["id"],
            "team_name": team["name"],
            # Back-compat single-namespace field: set only when unambiguous.
            "namespace": namespaces[0] if len(namespaces) == 1 else None,
            "namespaces": list(namespaces),
            "applications": apps,
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
        ingress = self._ingress_hosts(namespace)
        apps.extend(self._rollouts(namespace, rs_versions, ingress))
        apps.extend(self._deployments(namespace, ingress))
        apps.sort(key=lambda a: a["name"])

        with self._lock:
            self._cache[namespace] = {"apps": apps, "at": time.time()}
        return apps

    def _rollouts(
        self,
        namespace: str,
        rs_versions: Dict[str, Dict[str, str]],
        ingress: Dict[str, str],
    ) -> List[dict]:
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
            # The live host is served by the blue/green active Service.
            strategy = spec.get("strategy", {}) or {}
            active_service = (strategy.get("blueGreen", {}) or {}).get("activeService")
            if not active_service:
                active_service = (strategy.get("canary", {}) or {}).get("stableService")

            app = self._to_app(
                name=name,
                labels=meta.get("labels", {}),
                image=image,
                kind="Rollout",
                replicas=spec.get("replicas"),
                ready=status.get("readyReplicas"),
                annotations=meta.get("annotations", {}),
                serving_service=active_service,
                ingress=ingress,
            )
            app["rollout"] = self._rollout_status(spec, status, rs_versions.get(name, {}))
            # For a blue/green rollout the live version is the active one, which
            # differs from the spec image while a promotion is pending.
            repo = _repo_slug(meta.get("annotations", {}), image)
            if app["rollout"]:
                app["rollout"]["release_url"] = _release_url(repo, app["rollout"].get("active_version"))
                app["rollout"]["preview_release_url"] = _release_url(repo, app["rollout"].get("preview_version"))
                if app["rollout"].get("active_version"):
                    app["version"] = app["rollout"]["active_version"]
            app["release_url"] = _release_url(repo, app["version"])
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

    def _deployments(self, namespace: str, ingress: Dict[str, str]) -> List[dict]:
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
                annotations=dep.metadata.annotations or {},
                # A Deployment has no active/preview split; its Service usually
                # shares its name, so fall back to that when matching an ingress.
                serving_service=dep.metadata.name,
                ingress=ingress,
            ))
        return apps

    def _to_app(
        self,
        name,
        labels,
        image,
        kind,
        replicas,
        ready,
        annotations=None,
        serving_service=None,
        ingress=None,
    ) -> dict:
        labels = labels or {}
        annotations = annotations or {}
        ingress = ingress or {}
        component = labels.get(COMPONENT_LABEL)
        host = ingress.get(serving_service) if serving_service else ingress.get(name)
        version = _resolve_version(image, labels.get(VERSION_LABEL))
        return {
            "name": labels.get(NAME_LABEL) or name,
            "version": version,
            "kind": kind,
            "image": image,
            "replicas": replicas or 0,
            "ready_replicas": ready or 0,
            "part_of": labels.get(PART_OF_LABEL),
            "component": component,
            "url": self._app_url(host, component, annotations) if host else None,
            "release_url": _release_url(_repo_slug(annotations, image), version),
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

    def _ingress_hosts(self, namespace: str) -> Dict[str, str]:
        """Map backend-Service name -> external host for the ingresses in a
        namespace. Only the root ("/") path defines an app's canonical host, so
        a web ingress's extra "/api" path (routing to the API Service) doesn't
        steal the API app's own host."""
        result: Dict[str, str] = {}
        try:
            ings = self._net.list_namespaced_ingress(namespace)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not list ingresses in {namespace}: {e}")
            return result

        for ing in ings.items:
            for rule in ing.spec.rules or []:
                host = rule.host
                http = rule.http
                if not host or not http:
                    continue
                for path in http.paths or []:
                    if (path.path or "/") not in ("/", ""):
                        continue
                    svc = path.backend.service if path.backend else None
                    if svc and svc.name:
                        result[svc.name] = host
        return result

    def _app_url(self, host: str, component: Optional[str], annotations: dict) -> str:
        """Build the browser URL for an app from its ingress host: an "api" app
        links to its docs path (default /docs), anything else to its landing
        path (default /)."""
        base = f"{self._ingress_scheme}://{host}"
        default_https = self._ingress_scheme == "https" and self._ingress_port == "443"
        default_http = self._ingress_scheme == "http" and self._ingress_port == "80"
        if self._ingress_port and not (default_https or default_http):
            base = f"{base}:{self._ingress_port}"

        if component == "api":
            path = annotations.get(DOCS_PATH_ANNOTATION) or "/docs"
        else:
            path = annotations.get(URL_PATH_ANNOTATION) or "/"
        if not path.startswith("/"):
            path = "/" + path
        return base + path


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


def _image_repo_name(image: str) -> Optional[str]:
    """Extract the bare repo/image name from a reference, e.g.
    'harbor.example.com/platform/demo-api-go:2.2.0' -> 'demo-api-go'."""
    if not image:
        return None
    ref = image.split("@", 1)[0].split(":", 1)[0]
    name = ref.rsplit("/", 1)[-1]
    return name or None


def _repo_slug(annotations: dict, image: str) -> Optional[str]:
    """The GitHub "owner/repo" this workload's image is built from: the
    explicit override annotation if set, else the image name assumed to
    match the repo name (true for every standalone app repo so far)."""
    repo = (annotations or {}).get(SOURCE_REPO_ANNOTATION)
    if repo:
        return repo if "/" in repo else f"{GITHUB_ORG}/{repo}"
    name = _image_repo_name(image)
    return f"{GITHUB_ORG}/{name}" if name else None


def _release_url(repo_slug: Optional[str], version: Optional[str]) -> Optional[str]:
    """The GitHub release page for a deployed version, or None if either half
    is missing/meaningless (untagged image, no known source repo)."""
    if not repo_slug or not version or version in ("latest", "unknown"):
        return None
    tag = version if version.startswith("v") else f"v{version}"
    return f"https://github.com/{repo_slug}/releases/tag/{tag}"


def _resolve_version(image: str, label: Optional[str]) -> str:
    """Prefer the explicit image tag (source of truth after `set image`), then the
    app.kubernetes.io/version label, then the tagless fallback."""
    tag = _image_tag(image)
    if tag not in ("latest", "unknown"):
        return tag
    return label or tag
