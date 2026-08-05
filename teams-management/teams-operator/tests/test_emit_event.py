"""Regression test for the documented `_emit_event` gotcha (see CLAUDE.md):
it 422s on cluster-scoped or already-gone-namespace involvedObjects, and
that must stay a logged-and-swallowed failure, never something that
propagates and breaks the reconcile loop."""
from kubernetes.client.rest import ApiException


def test_emit_event_swallows_422(operator):
    operator.k8s_core_v1.create_namespaced_event.side_effect = ApiException(status=422, reason="Unprocessable Entity")

    # Must not raise, even though the underlying k8s call 422s.
    operator._emit_event(
        event_namespace="default",
        involved_namespace="some-cluster-scoped-thing",
        team_id="team-1",
        reason="RBACReady",
        message="doesn't matter",
    )

    operator.k8s_core_v1.create_namespaced_event.assert_called_once()


def test_emit_event_swallows_unexpected_error(operator):
    operator.k8s_core_v1.create_namespaced_event.side_effect = RuntimeError("boom")

    operator._emit_event(
        event_namespace="team-x",
        involved_namespace="team-x",
        team_id="team-1",
        reason="RBACReady",
        message="doesn't matter",
    )


def test_emit_event_cluster_scoped_object_stored_in_default(operator):
    """When event_namespace != involved_namespace (delete_namespace's case —
    the namespace is going away), the Event must be stored in `default` with
    a cluster-scoped (namespace=None) involvedObject, per apiserver's rule
    that a cluster-scoped involvedObject can't reference itself as
    namespaced. Confirms the code path this 422 protection wraps is doing
    the right thing, not just failing safe."""
    operator._emit_event(
        event_namespace="default",
        involved_namespace="team-being-deleted",
        team_id=None,
        reason="NamespaceDeleted",
        message="cleanup",
    )

    args, _ = operator.k8s_core_v1.create_namespaced_event.call_args
    store_namespace, body = args
    assert store_namespace == "default"
    assert body.involved_object.namespace is None
    assert body.involved_object.name == "team-being-deleted"
