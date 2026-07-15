"""
Per-application compliance for the Teams API.

Each app card in the portal gets a compliance badge that combines TWO sources:

  * Supply-chain evidence (verified offline) — read from the `app-compliance`
    ConfigMap, keyed by image ref. Each image carries policies like "Image
    signed", "SBOM attached", "No critical CVEs", "Quality checks passed",
    produced by supply-chain/compliance-report.sh (cosign verify + evidence
    parsing). See the supply-chain/ scripts.

  * Gatekeeper (live) — the platform's OPA/Gatekeeper constraints that actually
    govern this app's workload, attributed per-app from the same cluster scan the
    namespace badge uses (compliance.ComplianceChecker.scan()).

The two are merged into one badge (compliant / non_compliant / unknown) plus an
expandable per-policy list.
"""

import json
import logging
import os
import threading
import time
from typing import Dict, List, Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger("teams-api.app_compliance")

# Where the offline supply-chain report lives (teams-api's own namespace).
CM_NAMESPACE = os.getenv("POD_NAMESPACE", "engineering-platform")
CM_NAME = os.getenv("APP_COMPLIANCE_CONFIGMAP", "app-compliance")
CM_KEY = "report.json"
REPORT_TTL_SECONDS = 30

STATUS_COMPLIANT = "compliant"
STATUS_NON_COMPLIANT = "non_compliant"
STATUS_UNKNOWN = "unknown"


class AppComplianceReader:
    """Computes per-app compliance = supply-chain evidence + Gatekeeper."""

    def __init__(self, compliance_checker):
        # Reuse the namespace checker's cached Gatekeeper scan.
        self._cc = compliance_checker
        self._lock = threading.Lock()
        self._report: Dict[str, dict] = {}
        self._report_at: float = 0.0
        self._report_loaded = False
        self._k8s_ready = False

        try:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            self._core = client.CoreV1Api()
            self._k8s_ready = True
        except Exception as e:  # noqa: BLE001 - degrade gracefully
            logger.error(f"Kubernetes client unavailable, app compliance disabled: {e}")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def compliance_for(self, app: dict, namespace: Optional[str]) -> dict:
        """Combined compliance for one application (supply-chain + Gatekeeper)."""
        policies: List[dict] = []
        policies.extend(self._supply_chain_policies(app))
        policies.extend(self._gatekeeper_policies(app, namespace))

        if not policies:
            return {
                "status": STATUS_UNKNOWN,
                "reason": "No compliance evidence for this image yet",
                "total_policies": 0,
                "failing_policies": 0,
                "policies": [],
            }

        failing = sum(1 for p in policies if not p["compliant"])
        # Failing first, then supply-chain before gatekeeper, then by name.
        policies.sort(key=lambda p: (p["compliant"], p.get("category", ""), p["name"]))
        return {
            "status": STATUS_NON_COMPLIANT if failing else STATUS_COMPLIANT,
            "reason": None,
            "total_policies": len(policies),
            "failing_policies": failing,
            "policies": policies,
        }

    # ------------------------------------------------------------------ #
    # Supply-chain (offline report)
    # ------------------------------------------------------------------ #

    def _supply_chain_policies(self, app: dict) -> List[dict]:
        entry = self._get_report().get(app.get("image", ""))
        if not entry:
            return []
        # Copy so callers/sorting don't mutate the cache.
        return [dict(p) for p in entry.get("policies", [])]

    def _get_report(self) -> Dict[str, dict]:
        with self._lock:
            now = time.time()
            if self._report_loaded and (now - self._report_at) < REPORT_TTL_SECONDS:
                return self._report
        data = self._load_report()
        with self._lock:
            self._report = data
            self._report_at = time.time()
            self._report_loaded = True
        return data

    def _load_report(self) -> Dict[str, dict]:
        if not self._k8s_ready:
            return {}
        try:
            cm = self._core.read_namespaced_config_map(CM_NAME, CM_NAMESPACE)
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"Could not read {CM_NAMESPACE}/{CM_NAME}: {e.status}")
            return {}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Unexpected error reading {CM_NAMESPACE}/{CM_NAME}: {e}")
            return {}
        raw = (cm.data or {}).get(CM_KEY)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"Malformed {CM_KEY} in {CM_NAME}: {e}")
            return {}

    # ------------------------------------------------------------------ #
    # Gatekeeper (live, per-app attribution)
    # ------------------------------------------------------------------ #

    def _gatekeeper_policies(self, app: dict, namespace: Optional[str]) -> List[dict]:
        if not namespace:
            return []
        scan = self._cc.scan()
        if not scan.get("available"):
            return []

        out: List[dict] = []
        for c in scan.get("constraints", []):
            if not self._governs(c, namespace, app):
                continue
            viols = [
                v for v in c["violations"]
                if v.get("namespace") == namespace and self._refs_app(v, app)
            ]
            compliant = len(viols) == 0
            # Gatekeeper records one violation per Pod/replica (and one for the
            # Rollout), so a single logical finding — e.g. "coverage 0%" — repeats
            # across identical messages. De-duplicate by message for the card,
            # preserving first-seen order.
            messages = list(dict.fromkeys(
                v.get("message", "") for v in viols if v.get("message")
            ))
            out.append({
                "id": f"gk:{c['kind']}:{c['name']}",
                "name": c["name"],
                "category": "gatekeeper",
                "kind": c["kind"],
                "enforcement_action": c.get("enforcement_action", "deny"),
                "compliant": compliant,
                "detail": ("no violations" if compliant
                           else f"{len(messages)} violation(s)"),
                "messages": messages,
            })
        return out

    @staticmethod
    def _governs(constraint: dict, namespace: str, app: dict) -> bool:
        """Does this constraint actually apply to the app's workload?"""
        match_ns = constraint.get("match_namespaces") or []
        if match_ns and namespace not in match_ns:
            return False
        if namespace in (constraint.get("match_excluded_namespaces") or []):
            return False
        match_kinds = constraint.get("match_kinds") or []
        if match_kinds:
            kinds = {k for mk in match_kinds for k in (mk.get("kinds") or [])}
            # Apps produce Pods; also match the workload's own kind or a wildcard.
            if kinds and not (kinds & {"Pod", "*", app.get("kind", "")}):
                return False
        return True

    @staticmethod
    def _refs_app(violation: dict, app: dict) -> bool:
        """A violation belongs to this app if it names the app's workload or a
        Pod it owns (`<name>-<hash>-<rand>`)."""
        name = violation.get("name", "")
        app_name = app.get("name", "")
        return bool(app_name) and (name == app_name or name.startswith(app_name + "-"))
