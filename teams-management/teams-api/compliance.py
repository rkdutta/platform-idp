"""
Compliance checker for the Teams API.

Computes, per team, whether the team's Kubernetes namespace complies with the
platform-enforced Gatekeeper (OPA) constraints. Compliance is derived entirely
from the Kubernetes API:

  * ConstraintTemplates (templates.gatekeeper.sh/v1) tell us which constraint
    kinds exist.
  * The constraint objects for each kind (constraints.gatekeeper.sh/v1beta1,
    cluster-scoped) carry `status.violations[]`, each of which names the
    `namespace` it applies to.

A team is:
  * "compliant"      - constraints exist (or none do) and none report a
                       violation in the team's namespace.
  * "non_compliant"  - at least one constraint reports a violation in the
                       team's namespace.
  * "unknown"        - Gatekeeper is unreachable, or the team's namespace has
                       not been created yet (operator hasn't reconciled).

Falco (runtime) signals are intentionally out of scope here; a second checker
can be added behind the same status shape once a queryable Falco event sink
exists.
"""

import logging
import threading
import time
from typing import Dict, List, Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger("teams-api.compliance")

# Gatekeeper API coordinates.
TEMPLATE_GROUP = "templates.gatekeeper.sh"
TEMPLATE_VERSION = "v1"
CONSTRAINT_GROUP = "constraints.gatekeeper.sh"
CONSTRAINT_VERSION = "v1beta1"

# Label the teams-operator stamps on each team namespace.
TEAM_ID_LABEL = "teams.example.com/team-id"

# Compliance status values (kept as plain strings so the API/UI stay decoupled).
STATUS_COMPLIANT = "compliant"
STATUS_NON_COMPLIANT = "non_compliant"
STATUS_UNKNOWN = "unknown"

# How long a cluster scan is reused before being refreshed. The UI polls, so a
# small TTL keeps us from hammering the API server on every request.
SCAN_TTL_SECONDS = 15


class ComplianceChecker:
    """Reads Gatekeeper state and evaluates per-team namespace compliance."""

    def __init__(self):
        self._lock = threading.Lock()
        self._scan_cache: Optional[dict] = None
        self._scan_cache_at: float = 0.0
        self._k8s_ready = False

        try:
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except config.ConfigException:
                config.load_kube_config()
                logger.info("Loaded local kubeconfig")
            self._core = client.CoreV1Api()
            self._custom = client.CustomObjectsApi()
            self._k8s_ready = True
        except Exception as e:  # noqa: BLE001 - degrade gracefully, never crash the API
            logger.error(f"Kubernetes client unavailable, compliance will report 'unknown': {e}")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def summarize_all(self, teams: List[dict]) -> List[dict]:
        """Return a compact compliance summary for every team (badge data).

        Each `team` carries `namespaces` (already narrowed to what the caller may
        see); compliance is aggregated across them."""
        scan = self._get_scan()
        return [
            self._evaluate(team, team.get("namespaces") or [], scan, detailed=False)
            for team in teams
        ]

    def evaluate_team(self, team: dict) -> dict:
        """Return the detailed compliance breakdown for a single team, aggregated
        across the team's (in-scope) namespaces."""
        scan = self._get_scan()
        return self._evaluate(team, team.get("namespaces") or [], scan, detailed=True)

    def scan(self) -> dict:
        """Expose the cached cluster scan (constraints + violations + match
        scope) so per-app compliance can attribute Gatekeeper results."""
        return self._get_scan()

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #

    def _evaluate(self, team: dict, namespaces: List[str], scan: dict, detailed: bool) -> dict:
        base = {
            "team_id": team["id"],
            "team_name": team["name"],
            # Back-compat single-namespace field: set only when unambiguous.
            "namespace": namespaces[0] if len(namespaces) == 1 else None,
            "namespaces": list(namespaces),
            "checked_at": scan["checked_at"],
        }

        if not scan["available"]:
            return {**base, "status": STATUS_UNKNOWN,
                    "reason": scan.get("reason", "Gatekeeper is not reachable"),
                    "failing_policies": 0, "total_policies": 0,
                    **({"policies": []} if detailed else {})}

        if not namespaces:
            return {**base, "status": STATUS_UNKNOWN,
                    "reason": "Namespace not yet provisioned for this team",
                    "failing_policies": 0, "total_policies": len(scan["constraints"]),
                    **({"policies": []} if detailed else {})}

        ns_set = set(namespaces)
        multi = len(namespaces) > 1
        policies = []
        failing = 0
        for constraint in scan["constraints"]:
            # A constraint fails for the team if it is violated in ANY of the
            # team's (in-scope) namespaces.
            ns_violations = [
                v for v in constraint["violations"]
                if v.get("namespace") in ns_set
            ]
            is_compliant = len(ns_violations) == 0
            if not is_compliant:
                failing += 1
            if detailed:
                # Gatekeeper records one violation per Pod/replica; collapse
                # identical messages. When a team spans multiple namespaces,
                # prefix each message with the namespace it came from.
                messages = list(dict.fromkeys(
                    (f"[{v.get('namespace')}] {v.get('message', '')}" if multi
                     else v.get("message", ""))
                    for v in ns_violations if v.get("message")
                ))
                policies.append({
                    "name": constraint["name"],
                    "kind": constraint["kind"],
                    "enforcement_action": constraint["enforcement_action"],
                    "compliant": is_compliant,
                    "violation_count": len(messages),
                    "messages": messages,
                })

        status = STATUS_NON_COMPLIANT if failing else STATUS_COMPLIANT
        result = {**base, "status": status,
                  "failing_policies": failing,
                  "total_policies": len(scan["constraints"])}
        if detailed:
            # Failing policies first, then by name, for a stable, useful order.
            result["policies"] = sorted(policies, key=lambda p: (p["compliant"], p["name"]))
        return result

    # ------------------------------------------------------------------ #
    # Cluster reads
    # ------------------------------------------------------------------ #

    def _get_scan(self) -> dict:
        """Return a cached (per SCAN_TTL_SECONDS) scan of all Gatekeeper constraints."""
        with self._lock:
            now = time.time()
            if self._scan_cache is not None and (now - self._scan_cache_at) < SCAN_TTL_SECONDS:
                return self._scan_cache
            scan = self._scan_constraints()
            self._scan_cache = scan
            self._scan_cache_at = now
            return scan

    def _scan_constraints(self) -> dict:
        """List every Gatekeeper constraint and its per-namespace violations."""
        checked_at = _now_iso()
        if not self._k8s_ready:
            return {"available": False, "reason": "Kubernetes client unavailable",
                    "constraints": [], "checked_at": checked_at}

        # 1. Discover constraint kinds from the ConstraintTemplates.
        try:
            templates = self._custom.list_cluster_custom_object(
                TEMPLATE_GROUP, TEMPLATE_VERSION, "constrainttemplates"
            )
        except ApiException as e:
            if e.status == 404:
                # Gatekeeper CRDs absent -> we cannot assert compliance.
                return {"available": False, "reason": "Gatekeeper is not installed",
                        "constraints": [], "checked_at": checked_at}
            logger.error(f"Failed to list ConstraintTemplates: {e}")
            return {"available": False, "reason": f"Gatekeeper API error ({e.status})",
                    "constraints": [], "checked_at": checked_at}
        except Exception as e:  # noqa: BLE001
            logger.error(f"Unexpected error listing ConstraintTemplates: {e}")
            return {"available": False, "reason": "Gatekeeper is not reachable",
                    "constraints": [], "checked_at": checked_at}

        constraint_kinds = []
        for tmpl in templates.get("items", []):
            names = tmpl.get("spec", {}).get("crd", {}).get("spec", {}).get("names", {})
            kind = names.get("kind")
            if kind:
                # Gatekeeper serves each constraint kind under a lowercase plural.
                constraint_kinds.append((kind, kind.lower()))

        # 2. For each kind, list the constraint objects and collect violations.
        constraints = []
        for kind, plural in constraint_kinds:
            try:
                objs = self._custom.list_cluster_custom_object(
                    CONSTRAINT_GROUP, CONSTRAINT_VERSION, plural
                )
            except ApiException as e:
                # The CRD may not be established yet; skip this kind rather than fail.
                logger.warning(f"Could not list constraints of kind {kind} ({plural}): {e.status}")
                continue
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Unexpected error listing constraints of kind {kind}: {e}")
                continue

            for obj in objs.get("items", []):
                spec = obj.get("spec", {}) or {}
                status = obj.get("status", {}) or {}
                match = spec.get("match", {}) or {}
                constraints.append({
                    "name": obj.get("metadata", {}).get("name", ""),
                    "kind": kind,
                    "enforcement_action": spec.get("enforcementAction", "deny"),
                    "violations": status.get("violations", []) or [],
                    # Match scope, so per-app compliance can tell which apps a
                    # constraint actually governs.
                    "match_namespaces": match.get("namespaces") or [],
                    "match_excluded_namespaces": match.get("excludedNamespaces") or [],
                    "match_kinds": match.get("kinds") or [],
                })

        return {"available": True, "reason": None,
                "constraints": constraints, "checked_at": checked_at}

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


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
