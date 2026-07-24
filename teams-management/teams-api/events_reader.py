"""
Team activity feed for the Teams API.

Reads the Kubernetes Events teams-operator emits (see _emit_event /
_emit_condition_event in teams_operator.py) — namespace provisioning and
per-concern condition transitions (RBAC, ImagePullAccess, ResourceQuota,
LimitRange, NetworkPolicy, OpenBaoAccess) — and returns them aggregated
across a TEAM's namespaces, newest first. This is deliberately team-scoped,
not namespace-scoped: a team lead wants "what has the platform done for my
team", not one feed per namespace to cross-reference.

Only Events with source.component == "teams-operator" are returned — a
namespace also accumulates Events from kubelet, the scheduler, Gatekeeper,
etc., none of which are this feature's concern (and would drown out the
signal). Filtered client-side rather than via a field selector: the
core/v1 Events API's field-selector support doesn't reliably cover
`source.component`, and namespace-scoped Event volume is small enough that
listing and filtering in Python isn't a real cost.
"""

import logging
from typing import List

from kubernetes import client, config

logger = logging.getLogger("teams-api.events_reader")

OPERATOR_SOURCE = "teams-operator"


class TeamEventsReader:
    """Reads teams-operator's Events directly from the Kubernetes API —
    same client-bootstrap pattern as compliance.ComplianceChecker /
    provisioning_status.ProvisioningStatusChecker."""

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
            logger.error(f"Kubernetes client unavailable, team events will be empty: {e}")

    def events_for_team(self, team: dict, limit: int = 30) -> List[dict]:
        """Recent teams-operator Events across every namespace of `team`,
        newest last_timestamp first, capped at `limit` total."""
        if not self._k8s_ready:
            return []

        events = []
        for namespace in team.get("namespaces") or []:
            try:
                resp = self._core.list_namespaced_event(namespace)
            except Exception as e:  # noqa: BLE001 - a missing/unreadable namespace shouldn't blank the rest
                logger.warning(f"Could not list events in '{namespace}': {e}")
                continue

            for e in resp.items:
                source = e.source
                if not source or source.component != OPERATOR_SOURCE:
                    continue
                last_ts = e.last_timestamp or e.event_time or e.first_timestamp
                events.append({
                    "namespace": namespace,
                    "type": e.type or "Normal",
                    "reason": e.reason or "",
                    "message": e.message or "",
                    "count": e.count or 1,
                    "last_timestamp": last_ts.isoformat() if last_ts else None,
                })

        events.sort(key=lambda e: e["last_timestamp"] or "", reverse=True)
        return events[:limit]
