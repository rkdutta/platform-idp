"""Authorization resolution: what the caller may see and do.

Sits between auth.py (who is calling — from the JWT) and store.py (what they may
do — from the database). Every question here is answered by a live database read,
so a permission change takes effect on the caller's next request. That is the
whole point of moving authority out of the token.

The model:

- **admin** (realm role) — unrestricted. Bootstrap authority; see auth.require_admin.
- **project owner** (DB) — full control of that project's namespaces: order/delete them,
  and grant/revoke users within them. Ownership is per-project, so one user can own
  several projects and have no say in others.
- **namespace grant** (DB) — `maintainer` or `viewer` in one specific namespace.

Ownership implicitly confers `maintainer` on every namespace of the owned project.
That is *derived* on read rather than written as grant rows, so ownership and
per-namespace roles can never drift out of sync — adding a namespace to a project
automatically carries the owners' rights onto it.

Out-of-scope resources raise **404, not 403**: a 403 would confirm that a project
exists to someone who may not know it does.
"""

from __future__ import annotations

from typing import Optional, Set

from fastapi import HTTPException, Request

import store
from auth import caller_id, is_admin


def owned_project_ids(request: Request) -> Set[str]:
    """Projects the caller owns. Admins are handled separately (they own nothing but
    may do everything), so this is only meaningful alongside is_admin()."""
    return store.owned_project_ids(caller_id(request))


def is_owner(request: Request, project_id: str) -> bool:
    """True if the caller is an admin or an owner of this project."""
    return is_admin(request) or store.is_owner(caller_id(request), project_id)


def can_manage_project(request: Request, project_id: str) -> bool:
    """Alias of is_owner, named for the call sites that read as capability checks."""
    return is_owner(request, project_id)


def can_manage_namespace(request: Request, namespace: str) -> bool:
    """True if the caller may grant/revoke access in this namespace, i.e. they are
    an admin or own the project the namespace belongs to."""
    if is_admin(request):
        return True
    project = store.project_for_namespace(namespace)
    return project is not None and store.is_owner(caller_id(request), project["id"])


def visible_namespaces(request: Request) -> Optional[Set[str]]:
    """Namespaces the caller may see, or None for unrestricted (admin).

    The union of every namespace of every project they own and every namespace they
    hold an explicit grant on. An empty set means they see nothing — which is the
    correct default for a brand-new user.
    """
    if is_admin(request):
        return None
    uid = caller_id(request)
    out: Set[str] = set()
    for project_id in store.owned_project_ids(uid):
        out.update(store.namespaces_of(project_id))
    out.update(store.grants_for_user(uid).keys())
    return out


def namespace_role(request: Request, namespace: str) -> Optional[str]:
    """The caller's effective role in a namespace: 'maintainer', 'viewer' or None.

    Admins and project owners are maintainers everywhere they reach; otherwise the
    explicit grant decides.
    """
    if is_admin(request):
        return "maintainer"
    uid = caller_id(request)
    project = store.project_for_namespace(namespace)
    if project and store.is_owner(uid, project["id"]):
        return "maintainer"
    return store.grant_role(namespace, uid)


def scoped_projects(request: Request) -> list:
    """Projects the caller may see, each narrowed to their visible namespaces.

    Shape matches what workloads.py / compliance.py consume, so they need no
    changes: {id, name, created_at, namespaces:[...]}.

    Ownership grants visibility of the *project* in its own right, independent of
    namespace count — otherwise an owner who deletes their project's only
    namespace would lose the project from their own view (including the one
    place they could order a replacement namespace). Non-owned projects still
    only show up via an explicit namespace grant, narrowed to those namespaces.
    """
    if is_admin(request):
        return store.list_projects()
    owned = store.owned_project_ids(caller_id(request))
    scope = visible_namespaces(request)
    out = []
    for project in store.list_projects():
        if project["id"] in owned:
            out.append(project)
            continue
        visible = [ns for ns in project["namespaces"] if ns in scope]
        if visible:
            out.append({**project, "namespaces": visible})
    return out


def require_visible_project(request: Request, project_id: str) -> dict:
    """The project (narrowed to the caller's visible namespaces unless they own
    it, in which case they see it in full regardless of namespace count), or
    404."""
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if is_owner(request, project_id):
        return project
    scope = visible_namespaces(request)
    if scope is None:
        return project
    visible = [ns for ns in project["namespaces"] if ns in scope]
    if not visible:
        raise HTTPException(status_code=404, detail="Project not found")
    return {**project, "namespaces": visible}


def require_project_owner(request: Request, project_id: str) -> dict:
    """The full project record if the caller may manage it, else 404.

    404 rather than 403 so a non-owner cannot use this endpoint to discover which
    project ids exist.
    """
    project = store.get_project(project_id)
    if not project or not is_owner(request, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def require_namespace_manager(request: Request, namespace: str) -> dict:
    """The project owning `namespace` if the caller may manage access in it, else 404."""
    project = store.project_for_namespace(namespace)
    if not project or not can_manage_namespace(request, namespace):
        raise HTTPException(status_code=404, detail="Namespace not found")
    return project


def require_any_owner(request: Request) -> None:
    """Gate for the user-management surface (/users, /access): admins and anyone
    who owns at least one project. Non-owners have nobody to manage."""
    if is_admin(request) or owned_project_ids(request):
        return
    raise HTTPException(
        status_code=403, detail="Requires project ownership or the 'admin' role"
    )
