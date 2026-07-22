"""Authorization resolution: what the caller may see and do.

Sits between auth.py (who is calling — from the JWT) and store.py (what they may
do — from the database). Every question here is answered by a live database read,
so a permission change takes effect on the caller's next request. That is the
whole point of moving authority out of the token.

The model:

- **admin** (realm role) — unrestricted. Bootstrap authority; see auth.require_admin.
- **team owner** (DB) — full control of that team's namespaces: order/delete them,
  and grant/revoke users within them. Ownership is per-team, so one user can own
  several teams and have no say in others.
- **namespace grant** (DB) — `maintainer` or `viewer` in one specific namespace.

Ownership implicitly confers `maintainer` on every namespace of the owned team.
That is *derived* on read rather than written as grant rows, so ownership and
per-namespace roles can never drift out of sync — adding a namespace to a team
automatically carries the owners' rights onto it.

Out-of-scope resources raise **404, not 403**: a 403 would confirm that a team
exists to someone who may not know it does.
"""

from __future__ import annotations

from typing import Optional, Set

from fastapi import HTTPException, Request

import store
from auth import caller_id, is_admin


def owned_team_ids(request: Request) -> Set[str]:
    """Teams the caller owns. Admins are handled separately (they own nothing but
    may do everything), so this is only meaningful alongside is_admin()."""
    return store.owned_team_ids(caller_id(request))


def is_owner(request: Request, team_id: str) -> bool:
    """True if the caller is an admin or an owner of this team."""
    return is_admin(request) or store.is_owner(caller_id(request), team_id)


def can_manage_team(request: Request, team_id: str) -> bool:
    """Alias of is_owner, named for the call sites that read as capability checks."""
    return is_owner(request, team_id)


def can_manage_namespace(request: Request, namespace: str) -> bool:
    """True if the caller may grant/revoke access in this namespace, i.e. they are
    an admin or own the team the namespace belongs to."""
    if is_admin(request):
        return True
    team = store.team_for_namespace(namespace)
    return team is not None and store.is_owner(caller_id(request), team["id"])


def visible_namespaces(request: Request) -> Optional[Set[str]]:
    """Namespaces the caller may see, or None for unrestricted (admin).

    The union of every namespace of every team they own and every namespace they
    hold an explicit grant on. An empty set means they see nothing — which is the
    correct default for a brand-new user.
    """
    if is_admin(request):
        return None
    uid = caller_id(request)
    out: Set[str] = set()
    for team_id in store.owned_team_ids(uid):
        out.update(store.namespaces_of(team_id))
    out.update(store.grants_for_user(uid).keys())
    return out


def namespace_role(request: Request, namespace: str) -> Optional[str]:
    """The caller's effective role in a namespace: 'maintainer', 'viewer' or None.

    Admins and team owners are maintainers everywhere they reach; otherwise the
    explicit grant decides.
    """
    if is_admin(request):
        return "maintainer"
    uid = caller_id(request)
    team = store.team_for_namespace(namespace)
    if team and store.is_owner(uid, team["id"]):
        return "maintainer"
    return store.grant_role(namespace, uid)


def scoped_teams(request: Request) -> list:
    """Teams the caller may see, each narrowed to their visible namespaces.

    Shape matches what workloads.py / compliance.py consume, so they need no
    changes: {id, name, created_at, namespaces:[...]}.

    Ownership grants visibility of the *team* in its own right, independent of
    namespace count — otherwise an owner who deletes their team's only
    namespace would lose the team from their own view (including the one
    place they could order a replacement namespace). Non-owned teams still
    only show up via an explicit namespace grant, narrowed to those namespaces.
    """
    if is_admin(request):
        return store.list_teams()
    owned = store.owned_team_ids(caller_id(request))
    scope = visible_namespaces(request)
    out = []
    for team in store.list_teams():
        if team["id"] in owned:
            out.append(team)
            continue
        visible = [ns for ns in team["namespaces"] if ns in scope]
        if visible:
            out.append({**team, "namespaces": visible})
    return out


def require_visible_team(request: Request, team_id: str) -> dict:
    """The team (narrowed to the caller's visible namespaces unless they own
    it, in which case they see it in full regardless of namespace count), or
    404."""
    team = store.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if is_owner(request, team_id):
        return team
    scope = visible_namespaces(request)
    if scope is None:
        return team
    visible = [ns for ns in team["namespaces"] if ns in scope]
    if not visible:
        raise HTTPException(status_code=404, detail="Team not found")
    return {**team, "namespaces": visible}


def require_team_owner(request: Request, team_id: str) -> dict:
    """The full team record if the caller may manage it, else 404.

    404 rather than 403 so a non-owner cannot use this endpoint to discover which
    team ids exist.
    """
    team = store.get_team(team_id)
    if not team or not is_owner(request, team_id):
        raise HTTPException(status_code=404, detail="Team not found")
    return team


def require_namespace_manager(request: Request, namespace: str) -> dict:
    """The team owning `namespace` if the caller may manage access in it, else 404."""
    team = store.team_for_namespace(namespace)
    if not team or not can_manage_namespace(request, namespace):
        raise HTTPException(status_code=404, detail="Namespace not found")
    return team


def require_any_owner(request: Request) -> None:
    """Gate for the user-management surface (/users, /access): admins and anyone
    who owns at least one team. Non-owners have nobody to manage."""
    if is_admin(request) or owned_team_ids(request):
        return
    raise HTTPException(
        status_code=403, detail="Requires team ownership or the 'admin' role"
    )
