// src/app/components/users-page/users-page.component.ts
import { Component, OnInit } from "@angular/core";
import { TeamsService } from "../../services/teams.service";
import { AuthService } from "../../services/auth.service";
import {
  NamespaceAccess,
  NamespaceRole,
  Team,
  UserRef,
} from "../../models/team.model";

/** One namespace a user holds a role in, flattened for display. */
interface UserGrant {
  namespace: string;
  team_name: string;
  role: NamespaceRole;
  via: "owner" | "grant";
}

/**
 * User-centric access management — the only place either kind of access is
 * managed: per-namespace grants (viewer/maintainer, via /access) and team
 * ownership (via /teams/{id}/owners). The Teams page shows both read-only.
 *
 * The user list is the outer axis rather than the team: a namespace-centric panel
 * grows without bound as users are added, whereas here the page stays a filterable
 * table of people and you drill into one at a time.
 *
 * Everything is scoped by the API — /access only returns namespaces of teams the
 * caller owns (admins see all), so the pickers here can never offer a namespace
 * the caller isn't allowed to grant. Ownership add/remove is admin-only
 * server-side (require_admin on /teams/{id}/owners); non-admin owners see who
 * owns their team but can't change it.
 */
@Component({
  selector: "app-users-page",
  templateUrl: "./users-page.component.html",
  styleUrls: ["./users-page.component.css"],
})
export class UsersPageComponent implements OnInit {
  users: UserRef[] = [];
  access: NamespaceAccess[] = [];
  teams: Team[] = [];

  loading = true;
  error = "";
  saving = "";                       // user_id currently being written
  filter = "";

  expanded: { [userId: string]: boolean } = {};
  addNamespace: { [userId: string]: string } = {};
  addRole: { [userId: string]: NamespaceRole } = {};
  addTeamSel: { [userId: string]: string } = {};

  readonly roles: NamespaceRole[] = ["viewer", "maintainer"];

  /**
   * Access indexed by user, rebuilt only when /access or /teams changes.
   *
   * These MUST NOT be computed in the template. A method returning a fresh array
   * of fresh objects hands *ngFor new identities on every change-detection pass,
   * so it destroys and recreates every row — and the `ngModel` selects inside
   * those rows then trigger another pass, looping until the tab freezes.
   * Indexing once gives the arrays stable identity (and is far cheaper).
   */
  private grantsByUser: { [userId: string]: UserGrant[] } = {};
  private availableByUser: { [userId: string]: NamespaceAccess[] } = {};
  private ownedTeamsByUser: { [userId: string]: Team[] } = {};
  private assignableTeamsByUser: { [userId: string]: Team[] } = {};

  // Shared empty array: a fresh [] per call would defeat the stable identity above.
  private static readonly NONE: any[] = [];

  constructor(
    private teamsService: TeamsService,
    public authService: AuthService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.error = "";
    this.teamsService.getUsers().subscribe({
      next: (users) => {
        this.users = users;
        this.teamsService.getAccess().subscribe({
          next: (access) => {
            this.access = access;
            // Team ownership is sourced from /teams, not derived from /access:
            // a team with zero namespaces produces zero /access rows, but its
            // owner still needs to show up here (that's the whole point of
            // ownership being visibility in its own right — see authz.py).
            this.teamsService.getTeams().subscribe({
              next: (teams) => {
                this.teams = teams;
                this.indexAll();
                this.loading = false;
              },
              error: (err) => {
                this.error = `Could not load teams: ${err}`;
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

  /** Rebuild every per-user index. Call this (only) when access/teams change. */
  private indexAll(): void {
    this.grantsByUser = {};
    this.availableByUser = {};
    this.ownedTeamsByUser = {};
    this.assignableTeamsByUser = {};

    for (const ns of this.access) {
      for (const u of ns.users) {
        const list = this.grantsByUser[u.user_id] || (this.grantsByUser[u.user_id] = []);
        list.push({
          namespace: ns.namespace,
          team_name: ns.team_name,
          role: u.role,
          via: u.via,
        });
      }
    }

    // Namespaces the caller may grant, minus ones this user already holds
    // (whether via an explicit grant or via team ownership — both make the
    // "add a grant here" picker pointless for that namespace).
    for (const user of this.users) {
      const held = new Set((this.grantsByUser[user.id] || []).map((g) => g.namespace));
      this.availableByUser[user.id] = this.access.filter(
        (ns) => !held.has(ns.namespace),
      );
    }

    for (const team of this.teams) {
      for (const o of team.owners || []) {
        const list = this.ownedTeamsByUser[o.user_id] || (this.ownedTeamsByUser[o.user_id] = []);
        list.push(team);
      }
    }

    for (const user of this.users) {
      const owned = new Set((this.ownedTeamsByUser[user.id] || []).map((t) => t.id));
      this.assignableTeamsByUser[user.id] = this.teams.filter((t) => !owned.has(t.id));
    }
  }

  /** Every namespace this user holds a role in, across all visible teams. */
  grantsOf(user: UserRef): UserGrant[] {
    return this.grantsByUser[user.id] || UsersPageComponent.NONE;
  }

  /** Namespaces this user has no grant on yet — the "add" picker's options. */
  availableFor(user: UserRef): NamespaceAccess[] {
    return this.availableByUser[user.id] || UsersPageComponent.NONE;
  }

  /** Teams this user owns. */
  ownedTeamsOf(user: UserRef): Team[] {
    return this.ownedTeamsByUser[user.id] || UsersPageComponent.NONE;
  }

  /** Teams this user doesn't already own — the "add owner" picker's options. */
  assignableTeamsFor(user: UserRef): Team[] {
    return this.assignableTeamsByUser[user.id] || UsersPageComponent.NONE;
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
    this.teamsService.setAccess(namespace, user.id, role).subscribe({
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
    this.teamsService.revokeAccess(namespace, user.id).subscribe({
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

  /** Make this user an owner of a team (admin only server-side). */
  addOwnership(user: UserRef): void {
    const teamId = this.addTeamSel[user.id];
    if (!teamId) {
      return;
    }
    this.saving = user.id;
    this.error = "";
    this.teamsService.addOwner(teamId, user.id).subscribe({
      next: () => {
        this.saving = "";
        this.addTeamSel[user.id] = "";
        this.refreshAll();
      },
      error: (err) => {
        this.saving = "";
        this.error = `Could not make ${user.username} an owner: ${err}`;
      },
    });
  }

  removeOwnership(user: UserRef, team: Team): void {
    if (!confirm(`Remove ${user.username} as an owner of "${team.name}"?`)) {
      return;
    }
    this.saving = user.id;
    this.error = "";
    this.teamsService.removeOwner(team.id, user.id).subscribe({
      next: () => {
        this.saving = "";
        this.refreshAll();
      },
      error: (err) => {
        this.saving = "";
        this.error = `Could not remove ${user.username} from ${team.name}: ${err}`;
      },
    });
  }

  /** Re-read assignments + ownership — the Keycloak user directory hasn't
   *  changed, so /users isn't re-fetched. */
  private refreshAll(): void {
    this.teamsService.getAccess().subscribe({
      next: (access) => {
        this.access = access;
        this.teamsService.getTeams().subscribe({
          next: (teams) => {
            this.teams = teams;
            this.indexAll();
          },
          error: (err) => (this.error = `Could not reload teams: ${err}`),
        });
      },
      error: (err) => (this.error = `Could not reload access: ${err}`),
    });
  }
}
