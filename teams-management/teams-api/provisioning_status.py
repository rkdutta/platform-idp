"""
Namespace provisioning-status reader for the Teams API.

Reads the `teams.example.com/provisioning-status` annotation teams-operator
writes onto each namespace it manages, at the end of every reconcile cycle
(see update_namespace_status / the ensure_* methods in teams_operator.py) —
a JSON list of Kubernetes-style conditions, one per concern the operator
provisions (RBAC, ImagePullAccess, ResourceQuota, LimitRange, NetworkPolicy,
OpenBaoAccess), each `{type, status, reason, lastTransitionTime,
lastCheckedTime}`.

This is a passive read of teams-operator's own last-reconcile snapshot, not
a live probe of whether anything still actually works, and it never triggers
any repair — same reasoning as compliance.py's read-only Gatekeeper scan. A
namespace with no annotation yet (operator hasn't reconciled it, or predates
this feature) reports "unknown", not "broken" — silence isn't evidence of a
problem.
"""

import json
import logging
from typing import List, Optional

from kubernetes import client, config

logger = logging.getLogger("teams-api.provisioning_status")

STATUS_ANNOTATION = "teams.example.com/provisioning-status"

STATUS_READY = "ready"
STATUS_DEGRADED = "degraded"
STATUS_UNKNOWN = "unknown"


class ProvisioningStatusChecker:
    """Reads each namespace's provisioning-status annotation directly from
    the Kubernetes API — same client-bootstrap pattern as
    compliance.ComplianceChecker, kept as a separate reader since this reads
    Namespace objects, not Gatekeeper CRDs, and needs no cluster-wide scan
    (a namespace lookup is cheap and targeted, so no TTL cache like
    compliance.py's constraint scan)."""

    def __init__(self):
        self._k8s_ready = False
        try:
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except config.ConfigException:
                config.load_kube_config()
                logger.info("Loaded local kubeconfig")
            self._core = client.CoreV1Api()
            self._k8s_ready = True
        except Exception as e:  # noqa: BLE001 - degrade gracefully, never crash the API
            logger.error(f"Kubernetes client unavailable, provisioning status will report 'unknown': {e}")

    def summarize_all(self, teams: List[dict]) -> List[dict]:
        """One status entry per (team, namespace) pair, across every given
        team — mirrors compliance.py's summarize_all/applications_for_all
        bulk-fetch shape, so the portal can load every namespace's badge in
        one call instead of one round trip per namespace."""
        entries = []
        for team in teams:
            for namespace in team.get("namespaces") or []:
                entries.append(self._namespace_status(team["id"], team["name"], namespace))
        return entries

    def _namespace_status(self, team_id: str, team_name: str, namespace: str) -> dict:
        base = {"team_id": team_id, "team_name": team_name, "namespace": namespace}

        if not self._k8s_ready:
            return {**base, "status": STATUS_UNKNOWN,
                    "reason": "Kubernetes client unavailable", "conditions": []}

        try:
            ns = self._core.read_namespace(namespace)
        except Exception as e:  # noqa: BLE001 - includes 404 (not yet created) and transient API errors alike
            return {**base, "status": STATUS_UNKNOWN,
                    "reason": "Namespace not found or unreadable", "conditions": []}

        raw = (ns.metadata.annotations or {}).get(STATUS_ANNOTATION)
        if not raw:
            return {**base, "status": STATUS_UNKNOWN,
                    "reason": "teams-operator has not reconciled this namespace yet",
                    "conditions": []}

        try:
            conditions = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Malformed provisioning-status annotation on '{namespace}': {e}")
            return {**base, "status": STATUS_UNKNOWN,
                    "reason": "Malformed status annotation", "conditions": []}

        failing = [c for c in conditions if c.get("status") != "True"]
        status = STATUS_DEGRADED if failing else STATUS_READY
        if failing:
            reason = (
                f"{len(failing)} of {len(conditions)} checks not ready: "
                + ", ".join(c.get("type", "?") for c in failing)
            )
        elif conditions:
            # Ready still says *what* is ready, not just that nothing's
            # failing — otherwise the only way to see the individual checks
            # (RBAC, ImagePullAccess, ResourceQuota, LimitRange,
            # NetworkPolicy, OpenBaoAccess) is already-failing ones.
            reason = "All checks ready: " + ", ".join(c.get("type", "?") for c in conditions)
        else:
            reason = None
        return {**base, "status": status, "reason": reason, "conditions": conditions}
