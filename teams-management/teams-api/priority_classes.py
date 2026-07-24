"""
Tenant PriorityClass catalog for the Teams API.

Lists the PriorityClasses tenant workloads can be assigned (see
apps/resource/tenant-priority-classes), read live from the cluster rather
than hardcoded - if a tier is renamed, added, or removed there, this
reflects it on the next request with no code change here. Every tenant
workload actually gets one of these via a Gatekeeper mutation (see
apps/security/tenant-guardrails) if its own manifest doesn't set one, which
is what the application card's "Tier" field (workloads.py's priority_class)
shows per-app; this endpoint answers the different question "what tiers
exist to choose from."

The human-readable description per tier is NOT read from the cluster -
PriorityClass has no free-text field for it, and the actual scheduling
behavior it implies (which ResourceQuota bucket applies - see
teams-operator's quota-templates/) lives in a ConfigMap this service has no
reason to parse. Kept here as a short static map, matched to the tier names
by convention, not tier value - if a name doesn't match, a generic fallback
description is used rather than silently guessing.
"""

import logging
from typing import List

from kubernetes import client, config

logger = logging.getLogger("teams-api.priority_classes")

TIER_DESCRIPTIONS = {
    "tenant-critical": "Highest scheduling priority - reserved for workloads that must keep running.",
    "tenant-standard": "Default tier for typical production workloads.",
    "tenant-besteffort": "Lowest priority - first to be preempted under resource pressure; best for batch/dev workloads.",
}
DEFAULT_DESCRIPTION = "Tenant workload priority tier."


class PriorityClassCatalog:
    """Reads live PriorityClass objects — same client-bootstrap pattern as
    compliance.ComplianceChecker / provisioning_status.ProvisioningStatusChecker."""

    def __init__(self):
        self._k8s_ready = False
        try:
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except config.ConfigException:
                config.load_kube_config()
                logger.info("Loaded local kubeconfig")
            self._scheduling = client.SchedulingV1Api()
            self._k8s_ready = True
        except Exception as e:  # noqa: BLE001 - degrade gracefully, never crash the API
            logger.error(f"Kubernetes client unavailable, priority classes will be empty: {e}")

    def list_tenant_tiers(self) -> List[dict]:
        """Every PriorityClass whose name starts with `tenant-` (the
        platform's own tiers — cluster-admin/system PriorityClasses like
        `system-cluster-critical` aren't assignable to a tenant workload
        and would just be noise here), highest priority value first."""
        if not self._k8s_ready:
            return []
        try:
            resp = self._scheduling.list_priority_class()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not list PriorityClasses: {e}")
            return []

        tiers = [
            {
                "name": pc.metadata.name,
                "value": pc.value,
                "description": TIER_DESCRIPTIONS.get(pc.metadata.name, DEFAULT_DESCRIPTION),
            }
            for pc in resp.items
            if (pc.metadata.name or "").startswith("tenant-")
        ]
        tiers.sort(key=lambda t: t["value"], reverse=True)
        return tiers
