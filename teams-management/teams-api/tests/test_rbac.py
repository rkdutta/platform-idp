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


def _team(db, name="sss", team_id="t-sss"):
    return db.create_team(team_id, name, f"team-{name}")


# --------------------------------------------------------------------------- #
# Ownership
# --------------------------------------------------------------------------- #
def test_owner_manages_own_team_only(db, alice, bob):
    _team(db, "sss", "t-sss")
    _team(db, "mmm", "t-mmm")
    db.add_owner("t-sss", "alice-id", "alice")

    assert authz.is_owner(alice, "t-sss")
    assert not authz.is_owner(alice, "t-mmm")

    # A non-owner gets 404, not 403 — the endpoint must not confirm the team exists.
    assert authz.require_team_owner(alice, "t-sss")["name"] == "sss"
    with pytest.raises(HTTPException) as e:
        authz.require_team_owner(alice, "t-mmm")
    assert e.value.status_code == 404

    with pytest.raises(HTTPException):
        authz.require_team_owner(bob, "t-sss")


def test_owner_of_multiple_teams(db, alice):
    _team(db, "sss", "t-sss")
    _team(db, "mmm", "t-mmm")
    db.add_owner("t-sss", "alice-id", "alice")
    db.add_owner("t-mmm", "alice-id", "alice")

    assert authz.owned_team_ids(alice) == {"t-sss", "t-mmm"}
    assert {t["id"] for t in authz.scoped_teams(alice)} == {"t-sss", "t-mmm"}


def test_ownership_implies_maintainer_without_a_grant(db, alice):
    """The derived-not-stored rule: an owner is maintainer everywhere in the team,
    including namespaces added after they became owner."""
    _team(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")

    assert authz.namespace_role(alice, "team-sss") == "maintainer"
    assert db.grants_for_namespace("team-sss") == []  # nothing was written

    db.add_namespace("t-sss", "team-sss-staging")
    assert authz.namespace_role(alice, "team-sss-staging") == "maintainer"


def test_list_access_includes_owners_not_just_grants(db, alice, bob):
    """Regression test: GET /access (main.list_access) is what the Users page
    reads to show "which namespaces does this user have access to". An owner's
    maintainer access is derived (see test_ownership_implies_maintainer_without_a_grant
    above) rather than stored as a grant row, so a listing built from
    store.grants_for_namespace() alone silently drops every owner — they'd show
    zero namespaces despite having full access. list_access must merge in each
    team's owners."""
    import main  # noqa: PLC0415 - imported here, not at module scope, to avoid
    # paying FastAPI app construction for the tests above that don't need it.

    _team(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")
    db.set_grant("team-sss", "bob-id", "bob", "viewer")

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

    _team(db, "sss", "t-sss")
    db.set_grant("team-sss", "alice-id", "alice", "viewer")
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

    _team(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")
    db.set_grant("team-sss", "bob-id", "bob", "viewer")
    db.set_grant("team-sss", "carol-id", "carol", "maintainer")

    result = main.internal_access()
    assert result["admins"] == ["admin"]
    ns = result["namespaces"]["team-sss"]
    assert sorted(ns["viewer"]) == ["bob"]
    assert sorted(ns["maintainer"]) == ["alice", "carol"]


def test_internal_access_owner_not_duplicated_as_a_stale_grant(db, monkeypatch):
    """Same dedup rule as list_access: an owner who also holds a stale explicit
    grant appears once, as maintainer (via ownership), not twice."""
    import main  # noqa: PLC0415

    monkeypatch.setattr(main, "keycloak", _FakeKeycloak([]))

    _team(db, "sss", "t-sss")
    db.set_grant("team-sss", "alice-id", "alice", "viewer")
    db.add_owner("t-sss", "alice-id", "alice")

    ns = main.internal_access()["namespaces"]["team-sss"]
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
    _team(db, "sss", "t-sss")

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
    _team(db, "sss", "t-sss")

    main.grant_access(admin, main.AccessGrant(namespace="team-sss", user_id="bob", role="viewer"))

    assert fake_kc.group_members("team-sss-viewer") == ["bob"]
    assert fake_kc.group_members("team-sss-maintainer") == []


def test_grant_access_role_change_moves_between_groups(db, admin, monkeypatch):
    """viewer -> maintainer must remove from the old group, not just add to
    the new one — otherwise a former viewer grant lingers forever."""
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _team(db, "sss", "t-sss")

    main.grant_access(admin, main.AccessGrant(namespace="team-sss", user_id="bob", role="viewer"))
    main.grant_access(admin, main.AccessGrant(namespace="team-sss", user_id="bob", role="maintainer"))

    assert fake_kc.group_members("team-sss-viewer") == []
    assert fake_kc.group_members("team-sss-maintainer") == ["bob"]


def test_revoke_access_removes_from_group(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _team(db, "sss", "t-sss")
    main.grant_access(admin, main.AccessGrant(namespace="team-sss", user_id="bob", role="viewer"))

    main.revoke_access(admin, main.AccessGrant(namespace="team-sss", user_id="bob", role="viewer"))

    assert fake_kc.group_members("team-sss-viewer") == []


def test_grant_access_on_an_owner_has_no_group_effect(db, admin, monkeypatch):
    """Ownership always wins over an explicit grant (see internal_access's
    dedup) — granting an owner an explicit "viewer" role changes the DB row
    but must not demote their actual k8s access; they stay in -maintainer,
    never move to -viewer."""
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _team(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")
    fake_kc.add_user_to_group("alice", "team-sss-maintainer")  # what add_owner would have done

    main.grant_access(admin, main.AccessGrant(namespace="team-sss", user_id="alice", role="viewer"))

    assert fake_kc.group_members("team-sss-viewer") == []
    assert fake_kc.group_members("team-sss-maintainer") == ["alice"]


def test_add_owner_syncs_maintainer_group_for_every_namespace(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _team(db, "sss", "t-sss")
    db.add_namespace("t-sss", "team-sss-prod")

    main.add_owner(admin, "t-sss", main.OwnerAdd(user_id="alice"))

    assert fake_kc.group_members("team-sss-maintainer") == ["alice"]
    assert fake_kc.group_members("team-sss-prod-maintainer") == ["alice"]


def test_remove_owner_keeps_group_if_independent_grant_remains(db, admin, monkeypatch):
    """Removing ownership clears -maintainer everywhere *except* a namespace
    where the same user separately holds an explicit maintainer grant — that
    grant alone still justifies the group membership."""
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _team(db, "sss", "t-sss")
    db.add_namespace("t-sss", "team-sss-prod")
    main.add_owner(admin, "t-sss", main.OwnerAdd(user_id="alice"))
    main.grant_access(
        admin, main.AccessGrant(namespace="team-sss-prod", user_id="alice", role="maintainer")
    )

    main.remove_owner(admin, "t-sss", "alice-id")

    assert fake_kc.group_members("team-sss-maintainer") == []
    assert fake_kc.group_members("team-sss-prod-maintainer") == ["alice"]


def test_order_namespace_adds_existing_owners_to_new_namespace_group(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _team(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")

    asyncio.run(main.order_namespace(admin, "t-sss", main.NamespaceOrder(label="prod")))

    assert fake_kc.group_members("team-sss-prod-maintainer") == ["alice"]


def test_delete_namespace_cleans_up_k8s_groups(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _team(db, "sss", "t-sss")
    db.add_namespace("t-sss", "team-sss-prod")
    fake_kc.add_user_to_group("bob", "team-sss-prod-viewer")

    asyncio.run(main.delete_namespace(admin, "t-sss", "team-sss-prod"))

    assert "team-sss-prod-viewer" not in fake_kc.groups
    assert "team-sss-prod-maintainer" not in fake_kc.groups


def test_delete_team_cleans_up_k8s_groups_for_every_namespace(db, admin, monkeypatch):
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _team(db, "sss", "t-sss")
    db.add_namespace("t-sss", "team-sss-prod")
    fake_kc.add_user_to_group("bob", "team-sss-viewer")
    fake_kc.add_user_to_group("bob", "team-sss-prod-viewer")

    asyncio.run(main.delete_team(admin, "t-sss"))

    assert not fake_kc.groups.get("team-sss-viewer")
    assert not fake_kc.groups.get("team-sss-prod-viewer")


def test_group_reconciliation_corrects_drift(db, monkeypatch):
    """The self-healing backstop: given DB state that was never (or only
    partially) synced, one reconciliation pass brings Keycloak groups back
    in line — adding whoever's missing, removing whoever shouldn't be there."""
    import main  # noqa: PLC0415

    fake_kc = _FakeKeycloakDirectory()
    monkeypatch.setattr(main, "keycloak", fake_kc)
    _team(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")
    db.set_grant("team-sss", "bob-id", "bob", "viewer")
    # Drift: bob/alice were never actually synced, and carol is a stale
    # member who shouldn't be there at all.
    fake_kc.add_user_to_group("carol", "team-sss-viewer")

    main._reconcile_k8s_groups_once()

    assert fake_kc.group_members("team-sss-viewer") == ["bob"]
    assert fake_kc.group_members("team-sss-maintainer") == ["alice"]


def test_group_reconciliation_noop_when_keycloak_disabled(db, monkeypatch):
    """Must not raise (e.g. on a None-like fake) when Keycloak isn't
    configured — same degrade-gracefully posture as everywhere else."""
    import main  # noqa: PLC0415

    class DisabledKeycloak:
        enabled = False

    monkeypatch.setattr(main, "keycloak", DisabledKeycloak())
    _team(db, "sss", "t-sss")

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
    _team(db, "sss", "t-sss")
    assert authz.visible_namespaces(admin) is None
    assert authz.namespace_role(admin, "team-sss") == "maintainer"
    assert authz.is_owner(admin, "t-sss")


# --------------------------------------------------------------------------- #
# Default namespace: naming, and deletability
# --------------------------------------------------------------------------- #
def test_default_namespace_naming():
    import main  # noqa: PLC0415

    assert main.default_namespace("sss") == "team-sss-default"
    assert main.default_namespace("My Team!") == "team-my-team-default"


def test_default_namespace_naming_stays_within_63_chars():
    import main  # noqa: PLC0415

    ns = main.default_namespace("x" * 100)
    assert len(ns) <= 63
    assert ns.endswith("-default")


def test_default_namespace_of(db):
    _team(db, "sss", "t-sss")
    assert db.default_namespace_of("t-sss") == "team-sss"

    db.remove_namespace("team-sss")
    assert db.default_namespace_of("t-sss") is None


def test_owner_can_delete_the_default_namespace(db, alice):
    """The default namespace used to be permanently protected; it's now just a
    namespace like any other, deletable by its team's owner."""
    import main  # noqa: PLC0415

    _team(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")

    team = asyncio.run(main.delete_namespace(alice, "t-sss", "team-sss"))
    assert team.namespaces == []


def test_owner_keeps_seeing_a_team_with_zero_namespaces(db, alice):
    """Regression test: ownership must grant visibility of the team in its own
    right. Before this fix, scoped_teams/require_visible_team narrowed a team to
    its caller-visible *namespaces* — so an owner who deletes their team's only
    namespace would lose the team from their own view entirely, including the
    one place (order-namespace) they could recover from it."""
    import main  # noqa: PLC0415

    _team(db, "sss", "t-sss")
    db.add_owner("t-sss", "alice-id", "alice")
    asyncio.run(main.delete_namespace(alice, "t-sss", "team-sss"))

    teams = authz.scoped_teams(alice)
    assert len(teams) == 1
    assert teams[0]["id"] == "t-sss"
    assert teams[0]["namespaces"] == []

    visible = authz.require_visible_team(alice, "t-sss")
    assert visible["namespaces"] == []


# --------------------------------------------------------------------------- #
# Per-namespace roles
# --------------------------------------------------------------------------- #
def test_different_roles_in_different_namespaces(db, bob):
    """The requirement that motivated the redesign: viewer here, maintainer there."""
    _team(db, "sss", "t-sss")
    db.add_namespace("t-sss", "team-sss-prod")
    db.set_grant("team-sss", "bob-id", "bob", "viewer")
    db.set_grant("team-sss-prod", "bob-id", "bob", "maintainer")

    assert authz.namespace_role(bob, "team-sss") == "viewer"
    assert authz.namespace_role(bob, "team-sss-prod") == "maintainer"
    assert authz.visible_namespaces(bob) == {"team-sss", "team-sss-prod"}


def test_grant_is_an_upsert_not_a_duplicate(db, bob):
    _team(db, "sss", "t-sss")
    db.set_grant("team-sss", "bob-id", "bob", "viewer")
    db.set_grant("team-sss", "bob-id", "bob", "maintainer")

    grants = db.grants_for_namespace("team-sss")
    assert len(grants) == 1
    assert grants[0]["role"] == "maintainer"


def test_grantee_cannot_manage_access(db, bob):
    """A maintainer works *in* a namespace; managing who else gets in is the
    owner's job."""
    _team(db, "sss", "t-sss")
    db.set_grant("team-sss", "bob-id", "bob", "maintainer")

    assert not authz.can_manage_namespace(bob, "team-sss")
    with pytest.raises(HTTPException) as e:
        authz.require_namespace_manager(bob, "team-sss")
    assert e.value.status_code == 404


def test_user_with_no_grants_sees_nothing(db, bob):
    _team(db, "sss", "t-sss")
    assert authz.visible_namespaces(bob) == set()
    assert authz.scoped_teams(bob) == []
    assert authz.namespace_role(bob, "team-sss") is None
    with pytest.raises(HTTPException):
        authz.require_visible_team(bob, "t-sss")


def test_scoped_team_is_narrowed_to_granted_namespaces(db, bob):
    _team(db, "sss", "t-sss")
    db.add_namespace("t-sss", "team-sss-prod")
    db.set_grant("team-sss-prod", "bob-id", "bob", "viewer")

    teams = authz.scoped_teams(bob)
    assert len(teams) == 1
    assert teams[0]["namespaces"] == ["team-sss-prod"]  # team-sss hidden


def test_revoke_takes_effect_immediately(db, bob):
    _team(db, "sss", "t-sss")
    db.set_grant("team-sss", "bob-id", "bob", "viewer")
    assert authz.namespace_role(bob, "team-sss") == "viewer"

    db.remove_grant("team-sss", "bob-id")
    # Same request object — no new token, no refresh.
    assert authz.namespace_role(bob, "team-sss") is None


def test_grants_cascade_when_namespace_or_team_goes(db):
    _team(db, "sss", "t-sss")
    db.add_namespace("t-sss", "team-sss-prod")
    db.set_grant("team-sss-prod", "bob-id", "bob", "viewer")
    db.add_owner("t-sss", "alice-id", "alice")

    db.remove_namespace("team-sss-prod")
    assert db.grants_for_user("bob-id") == {}

    db.delete_team("t-sss")
    assert db.owned_team_ids("alice-id") == set()
    assert db.list_teams() == []


def test_invalid_role_rejected(db):
    _team(db, "sss", "t-sss")
    with pytest.raises(ValueError):
        db.set_grant("team-sss", "bob-id", "bob", "superuser")


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
                    "namespaces": ["team-sss", "team-sss-staging"],
                }
            ]
        )
    )
    groups = {"team-sss": ["teamlead1", "viewer1"], "team-sss-staging": ["teamlead1"]}
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
        default_namespace_of=lambda name: f"team-{name}",
    )


def test_migration_seeds_owners_and_grants(db, legacy):
    summary = _migrate(db, legacy)
    assert summary["status"] == "migrated"
    assert summary["teams"] == 1

    # The legacy team-leader becomes an OWNER; everyone else becomes a viewer.
    assert db.owned_team_ids("lead1-id") == {"t-sss"}
    assert db.grants_for_user("viewer1-id") == {"team-sss": "viewer"}
    assert db.grants_for_user("lead1-id") == {}  # ownership covers it

    # And access is preserved across the cutover, which is the whole point.
    lead = make_request("lead1-id", "teamlead1")
    assert authz.visible_namespaces(lead) == {"team-sss", "team-sss-staging"}
    assert authz.namespace_role(lead, "team-sss-staging") == "maintainer"

    viewer = make_request("viewer1-id", "viewer1")
    assert authz.visible_namespaces(viewer) == {"team-sss"}
    assert authz.namespace_role(viewer, "team-sss") == "viewer"


def test_migration_marks_the_default_namespace(db, legacy):
    _migrate(db, legacy)
    assert db.is_default_namespace("team-sss")
    assert not db.is_default_namespace("team-sss-staging")


def test_migration_is_idempotent(db, legacy):
    _migrate(db, legacy)
    again = _migrate(db, legacy)
    assert again["status"] == "already-migrated"
    assert len(db.list_teams()) == 1
    assert db.owned_team_ids("lead1-id") == {"t-sss"}


def test_migration_skips_users_missing_from_keycloak(db, tmp_path):
    """A group member with no Keycloak record can't be keyed on a sub — it is
    skipped and reported rather than stored against a guessed identity."""
    path = tmp_path / "teams.json"
    path.write_text(json.dumps([{"id": "t-x", "name": "x", "namespaces": ["team-x"]}]))
    summary = db.migrate_from_legacy_json(
        path,
        members_of=lambda ns: ["ghost"],
        users_by_name={},
        leaders=set(),
        default_namespace_of=lambda n: f"team-{n}",
    )
    assert summary["grants"] == 0
    assert "team-x:ghost" in summary["skipped"]


def test_startup_aborts_migration_when_keycloak_is_down(db, legacy, monkeypatch):
    """A Keycloak blip must not produce a permanently ownerless migration.

    Ownership and grants are derived from the directory, and the migration only
    runs on an empty database — so importing the teams without it would lock
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
    assert db.list_teams() == []


def test_migration_no_legacy_file(db, tmp_path):
    summary = db.migrate_from_legacy_json(
        tmp_path / "absent.json",
        members_of=lambda ns: [],
        users_by_name={},
        leaders=set(),
        default_namespace_of=lambda n: f"team-{n}",
    )
    assert summary["status"] == "no-legacy-data"


# --------------------------------------------------------------------------- #
# Audit + housekeeping
# --------------------------------------------------------------------------- #
def test_mutations_are_audited(db):
    _team(db, "sss", "t-sss")
    db.record("alice", "access.grant", "team-sss", "bob as viewer")
    tail = db.audit_tail()
    assert any(r["action"] == "access.grant" and r["actor"] == "alice" for r in tail)


def test_refresh_usernames_follows_a_rename(db):
    """Grants key on the sub, so a Keycloak rename must not orphan them."""
    _team(db, "sss", "t-sss")
    db.set_grant("team-sss", "bob-id", "bob", "viewer")
    db.add_owner("t-sss", "bob-id", "bob")

    db.refresh_usernames({"bob-id": "robert"})
    assert db.grants_for_namespace("team-sss")[0]["username"] == "robert"
    assert db.owners_of("t-sss")[0]["username"] == "robert"
