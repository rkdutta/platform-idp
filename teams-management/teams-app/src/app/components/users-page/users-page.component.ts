// src/app/components/users-page/users-page.component.ts
import { Component, OnInit } from "@angular/core";
import { TeamsService } from "../../services/teams.service";
import { AuthService } from "../../services/auth.service";
import {
  NamespaceAccess,
  NamespaceRole,
  UserRef,
} from "../../models/team.model";

/** One namespace a user holds a role in, flattened for display. */
interface UserGrant {
  namespace: string;
  team_name: string;
  role: NamespaceRole;
}

/**
 * User-centric access management.
 *
 * The user list is the outer axis rather than the team: a namespace-centric panel
 * grows without bound as users are added, whereas here the page stays a filterable
 * table of people and you drill into one at a time.
 *
 * Everything is scoped by the API — /access only returns namespaces of teams the
 * caller owns (admins see all), so the pickers here can never offer a namespace
 * the caller isn't allowed to grant.
 */
@Component({
  selector: "app-users-page",
  templateUrl: "./users-page.component.html",
  styleUrls: ["./users-page.component.css"],
})
export class UsersPageComponent implements OnInit {
  users: UserRef[] = [];
  access: NamespaceAccess[] = [];

  loading = true;
  error = "";
  saving = "";                       // user_id currently being written
  filter = "";

  expanded: { [userId: string]: boolean } = {};
  addNamespace: { [userId: string]: string } = {};
  addRole: { [userId: string]: NamespaceRole } = {};

  readonly roles: NamespaceRole[] = ["viewer", "maintainer"];

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
            this.loading = false;
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

  /** Every namespace this user holds a role in, across all visible teams. */
  grantsOf(user: UserRef): UserGrant[] {
    const out: UserGrant[] = [];
    for (const ns of this.access) {
      const hit = ns.users.find((u) => u.user_id === user.id);
      if (hit) {
        out.push({
          namespace: ns.namespace,
          team_name: ns.team_name,
          role: hit.role,
        });
      }
    }
    return out;
  }

  /** Namespaces this user has no grant on yet — the "add" picker's options. */
  availableFor(user: UserRef): NamespaceAccess[] {
    const held = new Set(this.grantsOf(user).map((g) => g.namespace));
    return this.access.filter((ns) => !held.has(ns.namespace));
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
        this.refreshAccess();
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
        this.refreshAccess();
      },
      error: (err) => {
        this.saving = "";
        this.error = `Could not revoke ${user.username} from ${namespace}: ${err}`;
      },
    });
  }

  /** Re-read assignments only — the Keycloak user directory hasn't changed. */
  private refreshAccess(): void {
    this.teamsService.getAccess().subscribe({
      next: (access) => (this.access = access),
      error: (err) => (this.error = `Could not reload access: ${err}`),
    });
  }
}
