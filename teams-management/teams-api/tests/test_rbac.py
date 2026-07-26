"""Authorization tests: ownership, per-namespace roles, and the 2.0 migration.

These exercise store.py + authz.py directly with a fake Request, which is where
all the access decisions actually live — no tokens or HTTP needed.
"""

import asyncio
import json
from typing import Dict, Set

import pytest
from fastapi import HTTPException

import authz
import store
from conftest import make_request


def _project(db, name="sss", project_id="t-sss"):
    return db.create_project(project_id, name, f"project-{name}")


# --------------------------------------------------------------------------- #
# Ownership
# --------------------------------------------------------------------------- #
def test_owner_manages_own_project_only(db, alice, bob):
    _project(db, "sss", "t-sss")
    _project(db, "mmm", "t-mmm")
    db.add_owner("t-sss", "alice-id", "alice")

    assert authz.is_owner(alice, "t-sss")
    assert not authz.is_owner(alice, "t-mmm")

    # A non-owner gets 404, not 403 — the endpoint must not confirm the project exists.
    assert authz.require_project_owner(alice, "t-sss")["name"] == "sss"
    with pytest.raises(HTTPException) as e:
        authz.require_project_owner(alice, "t-mmm")
    assert e.value.status_code == 404

    with pytest.raises(HTTPException):
        authz.require_project_owner(bob, "t-sss")


def test_owner_of_multiple_projects(db, alice):
    _project(db, "sss", "t-sss")
    _project(db, "mmm", "t-mmm")
    db.add_owner("t-sss", "alice-id", "alice")
    db.add_owner("t-mmm", "alice-id", "alice")

    assert authz.owned_project_ids(alice) == {"t-sss", "t-mmm"}
    assert {p["id"] for p in authz.scoped_projects(alice)} == {"t-sss", "t-mmm"}


def test_ownership_implies_maintainer_without_a_grant(db, alice):
    """The derived-not-stored rule: an owner is maintainer everywhere in the project,
    including namespaces added after they became owner."""
    _project(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")

    assert authz.namespace_role(alice, "project-sss") == "maintainer"
    assert db.grants_for_namespace("project-sss") == []  # nothing was written

    db.add_namespace("t-sss", "project-sss-staging")
    assert authz.namespace_role(alice, "project-sss-staging") == "maintainer"


def test_list_access_includes_owners_not_just_grants(db, alice, bob):
    """Regression test: GET /access (main.list_access) is what the Users page
    reads to show "which namespaces does this user have access to". An owner's
    maintainer access is derived (see test_ownership_implies_maintainer_without_a_grant
    above) rather than stored as a grant row, so a listing built from
    store.grants_for_namespace() alone silently drops every owner — they'd show
    zero namespaces despite having full access. list_access must merge in each
    project's owners."""
    import main  # noqa: PLC0415 - imported here, not at module scope, to avoid
    # paying FastAPI app construction for the tests above that don't need it.

    _project(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")
    db.set_grant("project-sss", "bob-id", "bob", "viewer")

    rows = main.list_access(alice)
    assert len(rows) == 1
    users = {u["user_id"]: u["role"] for u in rows[0]["users"]}
    assert users == {"alice-id": "maintainer", "bob-id": "viewer"}

    # `via` is what lets the Users page tell an implicit owner-row (nothing to
    # revoke there — see test below) apart from a real, revocable grant.
    via = {u["user_id"]: u["via"] for u in rows[0]["users"]}
    assert via == {"alice-id": "owner", "bob-id": "grant"}


def test_list_access_owner_entry_wins_over_a_stale_grant_row(db, alice):
    """An owner who also happens to hold an explicit grant row (e.g. left over
    from before they became owner) must appear once, as maintainer — not twice
    with conflicting roles."""
    import main  # noqa: PLC0415

    _project(db, "sss", "t-sss")
    db.set_grant("project-sss", "alice-id", "alice", "viewer")
    db.add_owner("t-sss", "alice-id", "alice")

    rows = main.list_access(alice)
    assert len(rows[0]["users"]) == 1
    assert rows[0]["users"][0]["role"] == "maintainer"
    assert rows[0]["users"][0]["via"] == "owner"


# --------------------------------------------------------------------------- #
# /internal/access — what teams-operator syncs into k8s RBAC
# --------------------------------------------------------------------------- #
class _FakeKeycloak:
    """Stands in for a reachable Keycloak admin client in /internal/access
    tests — only the bits internal_access() actually calls."""

    enabled = True

    def __init__(self, admins):
        self._admins = admins

    def role_members(self, role):
        return self._admins if role == "admin" else []


def test_internal_access_splits_viewer_and_maintainer_per_namespace(db, monkeypatch):
    import main  # noqa: PLC0415

    monkeypatch.setattr(main, "keycloak", _FakeKeycloak(["admin"]))

    _project(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")
    db.set_grant("project-sss", "bob-id", "bob", "viewer")
    db.set_grant("project-sss", "carol-id", "carol", "maintainer")

    result = main.internal_access()
    assert result["admins"] == ["admin"]
    ns = result["namespaces"]["project-sss"]
    assert sorted(ns["viewer"]) == ["bob"]
    assert sorted(ns["maintainer"]) == ["alice", "carol"]


def test_internal_access_owner_not_duplicated_as_a_stale_grant(db, monkeypatch):
    """Same dedup rule as list_access: an owner who also holds a stale explicit
    grant appears once, as maintainer (via ownership), not twice."""
    import main  # noqa: PLC0415

    monkeypatch.setattr(main, "keycloak", _FakeKeycloak([]))

    _project(db, "sss", "t-sss")
    db.set_grant("project-sss", "alice-id", "alice", "viewer")
    db.add_owner("t-sss", "alice-id", "alice")

    ns = main.internal_access()["namespaces"]["project-sss"]
    assert ns["viewer"] == []
    assert ns["maintainer"] == ["alice"]


def test_internal_access_admins_null_when_keycloak_unreachable(db, monkeypatch):
    """A Keycloak blip must not read as 'zero admins' — teams-operator treats
    null as 'leave the cluster-admin binding alone this cycle', [] as 'revoke
    everyone'. Those must never be confused."""
    import main  # noqa: PLC0415
    from keycloak_admin import KeycloakAdminError

    class DownKeycloak:
        enabled = True

        def role_members(self, role):
            raise KeycloakAdminError("connection refused")

    monkeypatch.setattr(main, "keycloak", DownKeycloak())
    _project(db, "sss", "t-sss")

    assert main.internal_access()["admins"] is None


# --------------------------------------------------------------------------- #
# k8s RBAC via Keycloak groups
#
# teams-operator binds two static RoleBindings per namespace to Group subjects
# named "{namespace}-viewer" / "{namespace}-maintainer" (see plan). teams-api
# is what keeps those groups' *membership* in sync with the DB — these tests
# exercise that sync directly against a fake Keycloak directory that both
# resolves users (like _lookup_user needs) and tracks group membership.
# --------------------------------------------------------------------------- #
class _FakeKeycloakDirectory:
    """Keycloak double good enough for main.py-level tests: resolves a small
    fixed user roster (so _lookup_user works) and tracks group membership
    (so tests can assert on it) without any network calls."""

    enabled = True

    def __init__(self):
        self._users = {
            "alice": {"id": "alice-id", "username": "alice"},
            "bob": {"id": "bob-id", "username": "bob"},
            "carol": {"id": "carol-id", "username": "carol"},
        }
        self.groups: Dict[str, Set[str]] = {}

    def list_users(self):
        return list(self._users.values())

    def role_members(self, role):
        return []

    def add_user_to_group(self, username, group):
        self.groups.setdefault(group, set()).add(username)

    def remove_user_from_group(self, username, group):
        self.groups.get(group, set()).discard(username)

    def delete_group(self, name):
        self.groups.pop(name, None)

    def group_members(self, name):
        return list(self.groups.get(name, set()))


def test_grant_access_syncs_k8s_group(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _project(db, "sss", "t-sss")

    main.grant_access(admin, main.AccessGrant(namespace="project-sss", user_id="bob", role="viewer"))

    assert fake_kc.group_members("project-sss-viewer") == ["bob"]
    assert fake_kc.group_members("project-sss-maintainer") == []


def test_grant_access_role_change_moves_between_groups(db, admin, monkeypatch):
    """viewer -> maintainer must remove from the old group, not just add to
    the new one — otherwise a former viewer grant lingers forever."""
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _project(db, "sss", "t-sss")

    main.grant_access(admin, main.AccessGrant(namespace="project-sss", user_id="bob", role="viewer"))
    main.grant_access(admin, main.AccessGrant(namespace="project-sss", user_id="bob", role="maintainer"))

    assert fake_kc.group_members("project-sss-viewer") == []
    assert fake_kc.group_members("project-sss-maintainer") == ["bob"]


def test_revoke_access_removes_from_group(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _project(db, "sss", "t-sss")
    main.grant_access(admin, main.AccessGrant(namespace="project-sss", user_id="bob", role="viewer"))

    main.revoke_access(admin, main.AccessGrant(namespace="project-sss", user_id="bob", role="viewer"))

    assert fake_kc.group_members("project-sss-viewer") == []


def test_grant_access_on_an_owner_has_no_group_effect(db, admin, monkeypatch):
    """Ownership always wins over an explicit grant (see internal_access's
    dedup) — granting an owner an explicit "viewer" role changes the DB row
    but must not demote their actual k8s access; they stay in -maintainer,
    never move to -viewer."""
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _project(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")
    fake_kc.add_user_to_group("alice", "project-sss-maintainer")  # what add_owner would have done

    main.grant_access(admin, main.AccessGrant(namespace="project-sss", user_id="alice", role="viewer"))

    assert fake_kc.group_members("project-sss-viewer") == []
    assert fake_kc.group_members("project-sss-maintainer") == ["alice"]


def test_add_owner_syncs_maintainer_group_for_every_namespace(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _project(db, "sss", "t-sss")
    db.add_namespace("t-sss", "project-sss-prod")

    main.add_owner(admin, "t-sss", main.OwnerAdd(user_id="alice"))

    assert fake_kc.group_members("project-sss-maintainer") == ["alice"]
    assert fake_kc.group_members("project-sss-prod-maintainer") == ["alice"]


def test_remove_owner_keeps_group_if_independent_grant_remains(db, admin, monkeypatch):
    """Removing ownership clears -maintainer everywhere *except* a namespace
    where the same user separately holds an explicit maintainer grant — that
    grant alone still justifies the group membership."""
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _project(db, "sss", "t-sss")
    db.add_namespace("t-sss", "project-sss-prod")
    main.add_owner(admin, "t-sss", main.OwnerAdd(user_id="alice"))
    main.grant_access(
        admin, main.AccessGrant(namespace="project-sss-prod", user_id="alice", role="maintainer")
    )

    main.remove_owner(admin, "t-sss", "alice-id")

    assert fake_kc.group_members("project-sss-maintainer") == []
    assert fake_kc.group_members("project-sss-prod-maintainer") == ["alice"]


def test_order_namespace_adds_existing_owners_to_new_namespace_group(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _project(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")

    asyncio.run(main.order_namespace(admin, "t-sss", main.NamespaceOrder(label="prod")))

    assert fake_kc.group_members("project-sss-prod-maintainer") == ["alice"]


def test_delete_namespace_cleans_up_k8s_groups(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _project(db, "sss", "t-sss")
    db.add_namespace("t-sss", "project-sss-prod")
    fake_kc.add_user_to_group("bob", "project-sss-prod-viewer")

    asyncio.run(main.delete_namespace(admin, "t-sss", "project-sss-prod"))

    assert "project-sss-prod-viewer" not in fake_kc.groups
    assert "project-sss-prod-maintainer" not in fake_kc.groups


def test_delete_project_cleans_up_k8s_groups_for_every_namespace(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _project(db, "sss", "t-sss")
    db.add_namespace("t-sss", "project-sss-prod")
    fake_kc.add_user_to_group("bob", "project-sss-viewer")
    fake_kc.add_user_to_group("bob", "project-sss-prod-viewer")

    asyncio.run(main.delete_project(admin, "t-sss"))

    assert not fake_kc.groups.get("project-sss-viewer")
    assert not fake_kc.groups.get("project-sss-prod-viewer")


def test_group_reconciliation_corrects_drift(db, monkeypatch):
    """The self-healing backstop: given DB state that was never (or only
    partially) synced, one reconciliation pass brings Keycloak groups back
    in line — adding whoever's missing, removing whoever shouldn't be there."""
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _project(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")
    db.set_grant("project-sss", "bob-id", "bob", "viewer")
    # Drift: bob/alice were never actually synced, and carol is a stale
    # member who shouldn't be there at all.
    fake_kc.add_user_to_group("carol", "project-sss-viewer")

    main._reconcile_k8s_groups_once()

    assert fake_kc.group_members("project-sss-viewer") == ["bob"]
    assert fake_kc.group_members("project-sss-maintainer") == ["alice"]


def test_group_reconciliation_noop_when_keycloak_disabled(db, monkeypatch):
    """Must not raise (e.g. on a None-like fake) when Keycloak isn't
    configured — same degrade-gracefully posture as everywhere else."""
    import main  # noqa: PLC0415

    class DisabledKeycloak:
        enabled = False

    monkeypatch.setattr(main, "keycloak", DisabledKeycloak())
    _project(db, "sss", "t-sss")

    main._reconcile_k8s_groups_once()  # must not raise


# --------------------------------------------------------------------------- #
# /kubeconfig
# --------------------------------------------------------------------------- #
def test_kubeconfig_renders_server_and_ca(db, monkeypatch):
    import base64

    import main  # noqa: PLC0415

    monkeypatch.setattr(main, "K8S_API_SERVER", "https://127.0.0.1:50706")
    monkeypatch.setattr(main, "K8S_API_CA_CERT", "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n")
    monkeypatch.setattr(main, "KEYCLOAK_CA_CERT", "-----BEGIN CERTIFICATE-----\nfakekc\n-----END CERTIFICATE-----\n")

    resp = main.get_kubeconfig()
    body = resp.body.decode()
    assert "server: https://127.0.0.1:50706" in body
    assert "command: kubectl" in body
    assert "- oidc-login" in body
    assert "- get-token" in body
    assert f"--oidc-issuer-url={main.OIDC_ISSUER}" in body
    assert "--oidc-client-id=teams-cli" in body
    assert "--listen-address=127.0.0.1:8400" in body

    # Both CAs are base64-encoded inline, not left as raw PEM (kubeconfig's
    # certificate-authority-data field, and kubelogin's --certificate-
    # authority-data flag, are both always base64).
    ca_line = next(l for l in body.splitlines() if l.strip().startswith("certificate-authority-data"))
    encoded = ca_line.split(": ", 1)[1]
    assert base64.b64decode(encoded).decode() == main.K8S_API_CA_CERT

    kc_ca_line = next(l for l in body.splitlines() if "--certificate-authority-data=" in l)
    kc_encoded = kc_ca_line.split("--certificate-authority-data=", 1)[1]
    assert base64.b64decode(kc_encoded).decode() == main.KEYCLOAK_CA_CERT


def test_kubeconfig_fails_loudly_when_unconfigured(db, monkeypatch):
    import main  # noqa: PLC0415

    monkeypatch.setattr(main, "K8S_API_SERVER", "")
    monkeypatch.setattr(main, "K8S_API_CA_CERT", "")
    monkeypatch.setattr(main, "KEYCLOAK_CA_CERT", "")

    with pytest.raises(HTTPException) as e:
        main.get_kubeconfig()
    assert e.value.status_code == 503


def test_kubeconfig_fails_loudly_when_only_keycloak_ca_missing(db, monkeypatch):
    """The kubelogin exec stanza needs Keycloak's CA too — partially configured
    (k8s side set, Keycloak side not) must still 503, not serve a kubeconfig
    that can authenticate to the cluster but never actually get a token."""
    import main  # noqa: PLC0415

    monkeypatch.setattr(main, "K8S_API_SERVER", "https://127.0.0.1:50706")
    monkeypatch.setattr(main, "K8S_API_CA_CERT", "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n")
    monkeypatch.setattr(main, "KEYCLOAK_CA_CERT", "")

    with pytest.raises(HTTPException) as e:
        main.get_kubeconfig()
    assert e.value.status_code == 503


def test_admin_is_unrestricted(db, admin):
    _project(db, "sss", "t-sss")
    assert authz.visible_namespaces(admin) is None
    assert authz.namespace_role(admin, "project-sss") == "maintainer"
    assert authz.is_owner(admin, "t-sss")


# --------------------------------------------------------------------------- #
# Default namespace: naming, and deletability
# --------------------------------------------------------------------------- #
def test_default_namespace_naming():
    import main  # noqa: PLC0415

    assert main.default_namespace("sss") == "project-sss-default"
    assert main.default_namespace("My Team!") == "project-my-team-default"


def test_default_namespace_naming_stays_within_63_chars():
    import main  # noqa: PLC0415

    ns = main.default_namespace("x" * 100)
    assert len(ns) <= 63
    assert ns.endswith("-default")


def test_default_namespace_of(db):
    _project(db, "sss", "t-sss")
    assert db.default_namespace_of("t-sss") == "project-sss"

    db.remove_namespace("project-sss")
    assert db.default_namespace_of("t-sss") is None


def test_owner_can_delete_the_default_namespace(db, alice):
    """The default namespace used to be permanently protected; it's now just a
    namespace like any other, deletable by its project's owner."""
    import main  # noqa: PLC0415

    _project(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")

    project = asyncio.run(main.delete_namespace(alice, "t-sss", "project-sss"))
    assert project.namespaces == []


def test_owner_keeps_seeing_a_project_with_zero_namespaces(db, alice):
    """Regression test: ownership must grant visibility of the project in its own
    right. Before this fix, scoped_projects/require_visible_project narrowed a project to
    its caller-visible *namespaces* — so an owner who deletes their project's only
    namespace would lose the project from their own view entirely, including the
    one place (order-namespace) they could recover from it."""
    import main  # noqa: PLC0415

    _project(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")
    asyncio.run(main.delete_namespace(alice, "t-sss", "project-sss"))

    projects = authz.scoped_projects(alice)
    assert len(projects) == 1
    assert projects[0]["id"] == "t-sss"
    assert projects[0]["namespaces"] == []

    visible = authz.require_visible_project(alice, "t-sss")
    assert visible["namespaces"] == []


# --------------------------------------------------------------------------- #
# Per-namespace roles
# --------------------------------------------------------------------------- #
def test_different_roles_in_different_namespaces(db, bob):
    """The requirement that motivated the redesign: viewer here, maintainer there."""
    _project(db, "sss", "t-sss")
    db.add_namespace("t-sss", "project-sss-prod")
    db.set_grant("project-sss", "bob-id", "bob", "viewer")
    db.set_grant("project-sss-prod", "bob-id", "bob", "maintainer")

    assert authz.namespace_role(bob, "project-sss") == "viewer"
    assert authz.namespace_role(bob, "project-sss-prod") == "maintainer"
    assert authz.visible_namespaces(bob) == {"project-sss", "project-sss-prod"}


def test_grant_is_an_upsert_not_a_duplicate(db, bob):
    _project(db, "sss", "t-sss")
    db.set_grant("project-sss", "bob-id", "bob", "viewer")
    db.set_grant("project-sss", "bob-id", "bob", "maintainer")

    grants = db.grants_for_namespace("project-sss")
    assert len(grants) == 1
    assert grants[0]["role"] == "maintainer"


def test_grantee_cannot_manage_access(db, bob):
    """A maintainer works *in* a namespace; managing who else gets in is the
    owner's job."""
    _project(db, "sss", "t-sss")
    db.set_grant("project-sss", "bob-id", "bob", "maintainer")

    assert not authz.can_manage_namespace(bob, "project-sss")
    with pytest.raises(HTTPException) as e:
        authz.require_namespace_manager(bob, "project-sss")
    assert e.value.status_code == 404


def test_user_with_no_grants_sees_nothing(db, bob):
    _project(db, "sss", "t-sss")
    assert authz.visible_namespaces(bob) == set()
    assert authz.scoped_projects(bob) == []
    assert authz.namespace_role(bob, "project-sss") is None
    with pytest.raises(HTTPException):
        authz.require_visible_project(bob, "t-sss")


def test_scoped_project_is_narrowed_to_granted_namespaces(db, bob):
    _project(db, "sss", "t-sss")
    db.add_namespace("t-sss", "project-sss-prod")
    db.set_grant("project-sss-prod", "bob-id", "bob", "viewer")

    projects = authz.scoped_projects(bob)
    assert len(projects) == 1
    assert projects[0]["namespaces"] == ["project-sss-prod"]  # project-sss hidden


def test_revoke_takes_effect_immediately(db, bob):
    _project(db, "sss", "t-sss")
    db.set_grant("project-sss", "bob-id", "bob", "viewer")
    assert authz.namespace_role(bob, "project-sss") == "viewer"

    db.remove_grant("project-sss", "bob-id")
    # Same request object — no new token, no refresh.
    assert authz.namespace_role(bob, "project-sss") is None


def test_grants_cascade_when_namespace_or_project_goes(db):
    _project(db, "sss", "t-sss")
    db.add_namespace("t-sss", "project-sss-prod")
    db.set_grant("project-sss-prod", "bob-id", "bob", "viewer")
    db.add_owner("t-sss", "alice-id", "alice")

    db.remove_namespace("project-sss-prod")
    assert db.grants_for_user("bob-id") == {}

    db.delete_project("t-sss")
    assert db.owned_project_ids("alice-id") == set()
    assert db.list_projects() == []


def test_invalid_role_rejected(db):
    _project(db, "sss", "t-sss")
    with pytest.raises(ValueError):
        db.set_grant("project-sss", "bob-id", "bob", "superuser")


# --------------------------------------------------------------------------- #
# Migration from the pre-2.0 JSON store + Keycloak groups
# --------------------------------------------------------------------------- #
@pytest.fixture
def legacy(tmp_path):
    """A teams.json plus the Keycloak group membership it relied on."""
    path = tmp_path / "teams.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "t-sss",
                    "name": "sss",
                    "created_at": "2026-01-01T00:00:00",
                    "namespaces": ["project-sss", "project-sss-staging"],
                }
            ]
        )
    )
    groups = {"project-sss": ["teamlead1", "viewer1"], "project-sss-staging": ["teamlead1"]}
    users = {
        "teamlead1": {"id": "lead1-id", "username": "teamlead1"},
        "viewer1": {"id": "viewer1-id", "username": "viewer1"},
    }
    return path, groups, users


def _migrate(db, legacy, leaders={"teamlead1"}):
    path, groups, users = legacy
    return db.migrate_from_legacy_json(
        path,
        members_of=lambda ns: groups.get(ns, []),
        users_by_name=users,
        leaders=leaders,
        default_namespace_of=lambda name: f"project-{name}",
    )


def test_migration_seeds_owners_and_grants(db, legacy):
    summary = _migrate(db, legacy)
    assert summary["status"] == "migrated"
    assert summary["teams"] == 1

    # The legacy team-leader becomes an OWNER; everyone else becomes a viewer.
    assert db.owned_project_ids("lead1-id") == {"t-sss"}
    assert db.grants_for_user("viewer1-id") == {"project-sss": "viewer"}
    assert db.grants_for_user("lead1-id") == {}  # ownership covers it

    # And access is preserved across the cutover, which is the whole point.
    lead = make_request("lead1-id", "teamlead1")
    assert authz.visible_namespaces(lead) == {"project-sss", "project-sss-staging"}
    assert authz.namespace_role(lead, "project-sss-staging") == "maintainer"

    viewer = make_request("viewer1-id", "viewer1")
    assert authz.visible_namespaces(viewer) == {"project-sss"}
    assert authz.namespace_role(viewer, "project-sss") == "viewer"


def test_migration_marks_the_default_namespace(db, legacy):
    _migrate(db, legacy)
    assert db.is_default_namespace("project-sss")
    assert not db.is_default_namespace("project-sss-staging")


def test_migration_is_idempotent(db, legacy):
    _migrate(db, legacy)
    again = _migrate(db, legacy)
    assert again["status"] == "already-migrated"
    assert len(db.list_projects()) == 1
    assert db.owned_project_ids("lead1-id") == {"t-sss"}


def test_migration_skips_users_missing_from_keycloak(db, tmp_path):
    """A group member with no Keycloak record can't be keyed on a sub — it is
    skipped and reported rather than stored against a guessed identity."""
    path = tmp_path / "teams.json"
    path.write_text(json.dumps([{"id": "t-x", "name": "x", "namespaces": ["project-x"]}]))
    summary = db.migrate_from_legacy_json(
        path,
        members_of=lambda ns: ["ghost"],
        users_by_name={},
        leaders=set(),
        default_namespace_of=lambda n: f"project-{n}",
    )
    assert summary["grants"] == 0
    assert "project-x:ghost" in summary["skipped"]


def test_startup_aborts_migration_when_keycloak_is_down(db, legacy, monkeypatch):
    """A Keycloak blip must not produce a permanently ownerless migration.

    Ownership and grants are derived from the directory, and the migration only
    runs on an empty database — so importing the projects without it would lock
    everyone out for good. Startup must leave the database untouched instead.
    """
    import main
    from keycloak_admin import KeycloakAdminError

    path, _, _ = legacy

    class DownKeycloak:
        enabled = True

        def list_users(self):
            raise KeycloakAdminError("connection refused")

        def role_members(self, role):
            raise KeycloakAdminError("connection refused")

        def group_members(self, ns):
            raise KeycloakAdminError("connection refused")

    monkeypatch.setattr(main, "keycloak", DownKeycloak())
    monkeypatch.setattr(main, "DATA_FILE", path)

    asyncio.run(main._startup())

    # Nothing imported, so the next restart retries with a healthy directory.
    assert db.list_projects() == []


def test_migration_no_legacy_file(db, tmp_path):
    summary = db.migrate_from_legacy_json(
        tmp_path / "absent.json",
        members_of=lambda ns: [],
        users_by_name={},
        leaders=set(),
        default_namespace_of=lambda n: f"project-{n}",
    )
    assert summary["status"] == "no-legacy-data"


# --------------------------------------------------------------------------- #
# Audit + housekeeping
# --------------------------------------------------------------------------- #
def test_mutations_are_audited(db):
    _project(db, "sss", "t-sss")
    db.record("alice", "access.grant", "project-sss", "bob as viewer")
    tail = db.audit_tail()
    assert any(r["action"] == "access.grant" and r["actor"] == "alice" for r in tail)


def test_refresh_usernames_follows_a_rename(db):
    """Grants key on the sub, so a Keycloak rename must not orphan them."""
    _project(db, "sss", "t-sss")
    db.set_grant("project-sss", "bob-id", "bob", "viewer")
    db.add_owner("t-sss", "bob-id", "bob")

    db.refresh_usernames({"bob-id": "robert"})
    assert db.grants_for_namespace("project-sss")[0]["username"] == "robert"
    assert db.owners_of("t-sss")[0]["username"] == "robert"
