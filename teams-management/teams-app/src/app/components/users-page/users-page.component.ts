// src/app/components/users-page/users-page.component.ts
import { Component, OnInit } from "@angular/core";
import { ProjectsService } from "../../services/projects.service";
import { AuthService } from "../../services/auth.service";
import {
  NamespaceAccess,
  NamespaceRole,
  Project,
  UserRef,
} from "../../models/project.model";

/** One namespace a user holds a role in, flattened for display. */
interface UserGrant {
  namespace: string;
  project_name: string;
  role: NamespaceRole;
  via: "owner" | "grant";
}

/**
 * User-centric access management — the only place either kind of access is
 * managed: per-namespace grants (viewer/maintainer, via /access) and project
 * ownership (via /projects/{id}/owners). The Projects page shows both read-only.
 *
 * The user list is the outer axis rather than the project: a namespace-centric panel
 * grows without bound as users are added, whereas here the page stays a filterable
 * table of people and you drill into one at a time.
 *
 * Everything is scoped by the API — /access only returns namespaces of projects the
 * caller owns (admins see all), so the pickers here can never offer a namespace
 * the caller isn't allowed to grant. Ownership add/remove is admin-only
 * server-side (require_admin on /projects/{id}/owners); non-admin owners see who
 * owns their project but can't change it.
 */
@Component({
  selector: "app-users-page",
  templateUrl: "./users-page.component.html",
  styleUrls: ["./users-page.component.css"],
})
export class UsersPageComponent implements OnInit {
  users: UserRef[] = [];
  access: NamespaceAccess[] = [];
  projects: Project[] = [];

  loading = true;
  error = "";
  saving = "";                       // user_id currently being written
  filter = "";

  expanded: { [userId: string]: boolean } = {};
  addNamespace: { [userId: string]: string } = {};
  addRole: { [userId: string]: NamespaceRole } = {};
  addProjectSel: { [userId: string]: string } = {};

  readonly roles: NamespaceRole[] = ["viewer", "maintainer"];

  /**
   * Access indexed by user, rebuilt only when /access or /projects changes.
   *
   * These MUST NOT be computed in the template. A method returning a fresh array
   * of fresh objects hands *ngFor new identities on every change-detection pass,
   * so it destroys and recreates every row — and the `ngModel` selects inside
   * those rows then trigger another pass, looping until the tab freezes.
   * Indexing once gives the arrays stable identity (and is far cheaper).
   */
  private grantsByUser: { [userId: string]: UserGrant[] } = {};
  private availableByUser: { [userId: string]: NamespaceAccess[] } = {};
  private ownedProjectsByUser: { [userId: string]: Project[] } = {};
  private assignableProjectsByUser: { [userId: string]: Project[] } = {};

  // Shared empty array: a fresh [] per call would defeat the stable identity above.
  private static readonly NONE: any[] = [];

  constructor(
    private projectsService: ProjectsService,
    public authService: AuthService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.error = "";
    this.projectsService.getUsers().subscribe({
      next: (users) => {
        this.users = users;
        this.projectsService.getAccess().subscribe({
          next: (access) => {
            this.access = access;
            // Project ownership is sourced from /projects, not derived from /access:
            // a project with zero namespaces produces zero /access rows, but its
            // owner still needs to show up here (that's the whole point of
            // ownership being visibility in its own right — see authz.py).
            this.projectsService.getProjects().subscribe({
              next: (projects) => {
                this.projects = projects;
                this.indexAll();
                this.loading = false;
              },
              error: (err) => {
                this.error = `Could not load projects: ${err}`;
                this.loading = false;
              },
            });
          },
          error: (err) => {
            this.error = `Could not load access: ${err}`;
            this.loading = false;
          },
        });
      },
      error: (err) => {
        this.error = `Could not load users: ${err}`;
        this.loading = false;
      },
    });
  }

  /** Namespaces the caller may grant — exactly what /access returned. */
  get manageableNamespaces(): NamespaceAccess[] {
    return this.access;
  }

  get filteredUsers(): UserRef[] {
    const q = this.filter.trim().toLowerCase();
    if (!q) {
      return this.users;
    }
    return this.users.filter((u) =>
      [u.username, u.firstName, u.lastName, u.email]
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }

  displayName(user: UserRef): string {
    const full = [user.firstName, user.lastName].filter(Boolean).join(" ");
    return full || user.username;
  }

  /** Rebuild every per-user index. Call this (only) when access/projects change. */
  private indexAll(): void {
    this.grantsByUser = {};
    this.availableByUser = {};
    this.ownedProjectsByUser = {};
    this.assignableProjectsByUser = {};

    for (const ns of this.access) {
      for (const u of ns.users) {
        const list = this.grantsByUser[u.user_id] || (this.grantsByUser[u.user_id] = []);
        list.push({
          namespace: ns.namespace,
          project_name: ns.project_name,
          role: u.role,
          via: u.via,
        });
      }
    }

    // Namespaces the caller may grant, minus ones this user already holds
    // (whether via an explicit grant or via project ownership — both make the
    // "add a grant here" picker pointless for that namespace).
    for (const user of this.users) {
      const held = new Set((this.grantsByUser[user.id] || []).map((g) => g.namespace));
      this.availableByUser[user.id] = this.access.filter(
        (ns) => !held.has(ns.namespace),
      );
    }

    for (const project of this.projects) {
      for (const o of project.owners || []) {
        const list = this.ownedProjectsByUser[o.user_id] || (this.ownedProjectsByUser[o.user_id] = []);
        list.push(project);
      }
    }

    for (const user of this.users) {
      const owned = new Set((this.ownedProjectsByUser[user.id] || []).map((p) => p.id));
      this.assignableProjectsByUser[user.id] = this.projects.filter((p) => !owned.has(p.id));
    }
  }

  /** Every namespace this user holds a role in, across all visible projects. */
  grantsOf(user: UserRef): UserGrant[] {
    return this.grantsByUser[user.id] || UsersPageComponent.NONE;
  }

  /** Namespaces this user has no grant on yet — the "add" picker's options. */
  availableFor(user: UserRef): NamespaceAccess[] {
    return this.availableByUser[user.id] || UsersPageComponent.NONE;
  }

  /** Projects this user owns. */
  ownedProjectsOf(user: UserRef): Project[] {
    return this.ownedProjectsByUser[user.id] || UsersPageComponent.NONE;
  }

  /** Projects this user doesn't already own — the "add owner" picker's options. */
  assignableProjectsFor(user: UserRef): Project[] {
    return this.assignableProjectsByUser[user.id] || UsersPageComponent.NONE;
  }

  // Stable identities for *ngFor, so a re-render can't recreate rows needlessly.
  trackByUser(_: number, user: UserRef): string {
    return user.id;
  }

  trackByNamespace(_: number, item: { namespace: string }): string {
    return item.namespace;
  }

  isPlatformAdmin(user: UserRef): boolean {
    return user.roles.includes("admin");
  }

  isProjectManager(user: UserRef): boolean {
    return user.roles.includes("project-manager");
  }

  toggle(user: UserRef): void {
    this.expanded[user.id] = !this.expanded[user.id];
  }

  isExpanded(user: UserRef): boolean {
    return !!this.expanded[user.id];
  }

  /** Grant a namespace, or change the role already held — the API upserts, so
   *  both are the same call. */
  setRole(user: UserRef, namespace: string, role: NamespaceRole): void {
    this.saving = user.id;
    this.error = "";
    this.projectsService.setAccess(namespace, user.id, role).subscribe({
      next: () => {
        this.saving = "";
        this.refreshAll();
      },
      error: (err) => {
        this.saving = "";
        this.error = `Could not update ${user.username} on ${namespace}: ${err}`;
      },
    });
  }

  addGrant(user: UserRef): void {
    const namespace = this.addNamespace[user.id];
    if (!namespace) {
      return;
    }
    this.setRole(user, namespace, this.addRole[user.id] || "viewer");
    this.addNamespace[user.id] = "";
  }

  revoke(user: UserRef, namespace: string): void {
    this.saving = user.id;
    this.error = "";
    this.projectsService.revokeAccess(namespace, user.id).subscribe({
      next: () => {
        this.saving = "";
        this.refreshAll();
      },
      error: (err) => {
        this.saving = "";
        this.error = `Could not revoke ${user.username} from ${namespace}: ${err}`;
      },
    });
  }

  /** Make this user an owner of a project (admin only server-side). */
  addOwnership(user: UserRef): void {
    const projectId = this.addProjectSel[user.id];
    if (!projectId) {
      return;
    }
    this.saving = user.id;
    this.error = "";
    this.projectsService.addOwner(projectId, user.id).subscribe({
      next: () => {
        this.saving = "";
        this.addProjectSel[user.id] = "";
        this.refreshAll();
      },
      error: (err) => {
        this.saving = "";
        this.error = `Could not make ${user.username} an owner: ${err}`;
      },
    });
  }

  removeOwnership(user: UserRef, project: Project): void {
    if (!confirm(`Remove ${user.username} as an owner of "${project.name}"?`)) {
      return;
    }
    this.saving = user.id;
    this.error = "";
    this.projectsService.removeOwner(project.id, user.id).subscribe({
      next: () => {
        this.saving = "";
        this.refreshAll();
      },
      error: (err) => {
        this.saving = "";
        this.error = `Could not remove ${user.username} from ${project.name}: ${err}`;
      },
    });
  }

  /** Grant the `project-manager` realm role (admin-only server-side) — lets this
   *  user self-service create projects without needing an admin to do it for them.
   *  Unlike addOwnership/removeOwnership/setRole, this changes `user.roles`
   *  itself, so /users (not just /access + /projects) needs re-fetching. */
  grantProjectManager(user: UserRef): void {
    this.saving = user.id;
    this.error = "";
    this.projectsService.grantProjectManager(user.id).subscribe({
      next: () => {
        this.saving = "";
        this.refreshUsersAndAll();
      },
      error: (err) => {
        this.saving = "";
        this.error = `Could not make ${user.username} a project manager: ${err}`;
      },
    });
  }

  revokeProjectManager(user: UserRef): void {
    this.saving = user.id;
    this.error = "";
    this.projectsService.revokeProjectManager(user.id).subscribe({
      next: () => {
        this.saving = "";
        this.refreshUsersAndAll();
      },
      error: (err) => {
        this.saving = "";
        this.error = `Could not remove ${user.username} as project manager: ${err}`;
      },
    });
  }

  /** refreshAll() plus /users — for the one action (project-manager grant/revoke)
   *  that actually changes a UserRef's roles array. */
  private refreshUsersAndAll(): void {
    this.projectsService.getUsers().subscribe({
      next: (users) => (this.users = users),
      error: (err) => (this.error = `Could not reload users: ${err}`),
    });
    this.refreshAll();
  }

  /** Re-read assignments + ownership — the Keycloak user directory hasn't
   *  changed, so /users isn't re-fetched. */
  private refreshAll(): void {
    this.projectsService.getAccess().subscribe({
      next: (access) => {
        this.access = access;
        this.projectsService.getProjects().subscribe({
          next: (projects) => {
            this.projects = projects;
            this.indexAll();
          },
          error: (err) => (this.error = `Could not reload projects: ${err}`),
        });
      },
      error: (err) => (this.error = `Could not reload access: ${err}`),
    });
  }
}
