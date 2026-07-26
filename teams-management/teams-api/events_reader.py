"""
Project activity feed for the Teams API.

Reads the Kubernetes Events teams-operator emits (see _emit_event /
_emit_condition_event in teams_operator.py) — namespace provisioning/
deletion and per-concern condition transitions (RBAC, ImagePullAccess,
ResourceQuota, LimitRange, NetworkPolicy, OpenBaoAccess) — and returns them
aggregated for a PROJECT, newest first. This is deliberately project-scoped, not
namespace-scoped: a project lead wants "what has the platform done for my
project", not one feed per namespace to cross-reference.

Queried cluster-wide (list_event_for_all_namespaces) by the
`teams.example.com/team-id` label every Event teams-operator emits carries,
rather than iterating the project's current namespace list — that's the only
way to also catch "namespace deleted" Events, which teams-operator stores
in its own (durable) namespace precisely because the namespace they're
*about* no longer exists to hold them (see OPERATOR_NAMESPACE in
teams_operator.py). Filtering by the project's current namespaces would miss
exactly the events about a namespace that just stopped being current.

Also filtered (client-side, defense in depth alongside the label) to
source.component == "teams-operator" — a namespace/cluster also accumulates
Events from kubelet, the scheduler, Gatekeeper, etc., none of which are
this feature's concern.
"""

import logging
from typing import List

from kubernetes import client, config

logger = logging.getLogger("teams-api.events_reader")

OPERATOR_SOURCE = "teams-operator"
# The label key itself is an external contract with teams-operator (unchanged);
# only this Python identifier is renamed to match the project vocabulary.
PROJECT_ID_LABEL = "teams.example.com/team-id"


class ProjectEventsReader:
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
            logger.error(f"Kubernetes client unavailable, project events will be empty: {e}")

    def events_for_project(self, project: dict, limit: int = 30) -> List[dict]:
        """Recent teams-operator Events for `project`, newest last_timestamp
        first, capped at `limit` total."""
        if not self._k8s_ready:
            return []

        try:
            resp = self._core.list_event_for_all_namespaces(
                label_selector=f"{PROJECT_ID_LABEL}={project['id']}"
            )
        except Exception as e:  # noqa: BLE001 - a listing hiccup shouldn't break the whole response
            logger.warning(f"Could not list events for project '{project['id']}': {e}")
            return []

        events = []
        for e in resp.items:
            source = e.source
            if not source or source.component != OPERATOR_SOURCE:
                continue
            involved = e.involved_object
            last_ts = e.last_timestamp or e.event_time or e.first_timestamp
            events.append({
                # The involvedObject's namespace, not the Event's own
                # metadata.namespace — those differ for deletion Events
                # (stored in OPERATOR_NAMESPACE, about a namespace that's
                # gone), and the UI wants "which namespace was this about."
                "namespace": involved.namespace if involved else "",
                "type": e.type or "Normal",
                "reason": e.reason or "",
                "message": e.message or "",
                "count": e.count or 1,
                "last_timestamp": last_ts.isoformat() if last_ts else None,
            })

        events.sort(key=lambda e: e["last_timestamp"] or "", reverse=True)
        return events[:limit]
