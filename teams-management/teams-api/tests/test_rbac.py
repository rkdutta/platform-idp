"""Authorization tests: ownership, per-namespace roles, and the 2.0 migration.

These exercise store.py + authz.py directly with a fake Request, which is where
all the access decisions actually live — no tokens or HTTP needed.
"""

import json

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


def test_admin_is_unrestricted(db, admin):
    _team(db, "sss", "t-sss")
    assert authz.visible_namespaces(admin) is None
    assert authz.namespace_role(admin, "team-sss") == "maintainer"
    assert authz.is_owner(admin, "t-sss")


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

    main._startup()

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
