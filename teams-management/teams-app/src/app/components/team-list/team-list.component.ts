import { Component, OnInit } from "@angular/core";
import { TeamsService } from "../../services/teams.service";
import { AuthService } from "../../services/auth.service";
import { environment } from "../../../environments/environment";
import {
  Team,
  ComplianceStatus,
  ComplianceSummary,
  ComplianceDetail,
  Application,
  ApplicationGroup,
  UserRef,
  NamespaceAccess,
} from "../../models/team.model";

@Component({
  selector: "app-team-list",
  templateUrl: "./team-list.component.html",
  styleUrls: ["./team-list.component.css"],
})
export class TeamListComponent implements OnInit {
  teams: Team[] = [];
  isLoading = true;
  errorMessage = "";

  // Compliance state, keyed by team id.
  compliance: { [teamId: string]: ComplianceSummary } = {};
  complianceDetail: { [teamId: string]: ComplianceDetail } = {};
  expanded: { [teamId: string]: boolean } = {};
  loadingDetail: { [teamId: string]: boolean } = {};

  // Applications running in each team's namespace, keyed by team id, already
  // grouped by app.kubernetes.io/part-of into application cards.
  appGroups: { [teamId: string]: ApplicationGroup[] } = {};

  // Application groups keyed by team id THEN namespace, so each namespace card
  // renders only the apps running in it.
  appGroupsByNs: { [teamId: string]: { [namespace: string]: ApplicationGroup[] } } = {};

  // Each team's namespace, keyed by team id (for Rollouts dashboard deep links).
  teamNamespace: { [teamId: string]: string | null } = {};

  // Expansion state per team id. Cards start COLLAPSED, so the list stays
  // scannable (each collapsed card still shows its compliance badge); an entry
  // is only present once the user has toggled that card.
  collapsed: { [teamId: string]: boolean } = {};

  // --- Access management (team-leader / admin only) ---
  // namespace -> usernames who can see it (scoped to the caller's owned teams).
  accessByNs: { [namespace: string]: string[] } = {};
  // The full Keycloak user pool for the assignment picker.
  allUsers: UserRef[] = [];
  // Per-team "order namespace" label input.
  orderLabel: { [teamId: string]: string } = {};
  // Per-namespace selected user in the add-user picker.
  addUserSel: { [namespace: string]: string } = {};
  accessError = "";

  // public so the template can gate the Delete button on manage rights.
  constructor(
    private teamsService: TeamsService,
    public authService: AuthService,
  ) {}

  ngOnInit() {
    this.loadTeams();
  }

  loadTeams() {
    this.isLoading = true;
    this.errorMessage = "";
    // Clear any stale access banner; loadAccess/loadUsers below re-set it only if
    // they fail again, so a recovered backend makes the banner disappear.
    this.accessError = "";

    this.teamsService.getTeams().subscribe({
      next: (teams) => {
        this.teams = teams;
        this.isLoading = false;
        this.loadCompliance();
        this.loadApplications();
        if (this.authService.canManage()) {
          this.loadAccess();
          this.loadUsers();
        }
      },
      error: (error) => {
        this.errorMessage = error;
        this.isLoading = false;
      },
    });
  }

  toggleCollapse(teamId: string) {
    this.collapsed[teamId] = !this.isCollapsed(teamId);
  }

  // Default is collapsed: only an explicit `false` counts as expanded.
  isCollapsed(teamId: string): boolean {
    return this.collapsed[teamId] !== false;
  }

  // --- Access management --------------------------------------------------
  loadAccess() {
    this.teamsService.getAccess().subscribe({
      next: (rows) => {
        this.accessByNs = {};
        for (const row of rows) {
          this.accessByNs[row.namespace] = row.users;
        }
      },
      error: (error) => console.error("Failed to load access:", error),
    });
  }

  loadUsers() {
    this.teamsService.getUsers().subscribe({
      next: (users) => (this.allUsers = users),
      // Surface this: an empty picker usually means the Keycloak admin client
      // (teams-api-sa) isn't reachable/authorized, not "no users".
      error: (error) => (this.accessError = "Could not load users: " + error),
    });
  }

  usersFor(namespace: string): string[] {
    return this.accessByNs[namespace] || [];
  }

  // Users not already granted the namespace — the pool the picker offers.
  assignableUsers(namespace: string): UserRef[] {
    const granted = new Set(this.usersFor(namespace));
    return this.allUsers.filter((u) => !granted.has(u.username));
  }

  // The app realm roles for a username (from the loaded user pool), e.g. for
  // showing "teamlead1 (team-leader)" next to an assigned member.
  rolesOf(username: string): string[] {
    return this.allUsers.find((u) => u.username === username)?.roles || [];
  }

  roleLabel(username: string): string {
    const roles = this.rolesOf(username);
    return roles.length ? roles.join(", ") : "";
  }

  orderNamespace(team: Team) {
    const label = (this.orderLabel[team.id] || "").trim();
    if (!label) {
      return;
    }
    this.accessError = "";
    this.teamsService.orderNamespace(team.id, label).subscribe({
      next: () => {
        this.orderLabel[team.id] = "";
        // The API auto-grants the ordering user the new namespace's Keycloak
        // group; force a token refresh so the new `groups` claim lands and the
        // namespace becomes visible to them immediately (no re-login).
        this.authService.forceRefresh().then(() => this.loadTeams());
      },
      error: (error) => (this.accessError = error),
    });
  }

  // The team's default namespace (index 0) can't be deleted — only ordered ones.
  isDefaultNamespace(team: Team, namespace: string): boolean {
    return team.namespaces[0] === namespace;
  }

  deleteNamespace(team: Team, namespace: string) {
    if (
      !confirm(
        `Delete namespace "${namespace}"? This removes the namespace and everything running in it.`,
      )
    ) {
      return;
    }
    this.accessError = "";
    this.teamsService.deleteNamespace(team.id, namespace).subscribe({
      next: () => this.loadTeams(),
      error: (error) => (this.accessError = error),
    });
  }

  grant(namespace: string) {
    const username = this.addUserSel[namespace];
    if (!username) {
      return;
    }
    this.accessError = "";
    this.teamsService.grantAccess(namespace, username).subscribe({
      next: () => {
        this.addUserSel[namespace] = "";
        this.loadAccess();
      },
      error: (error) => (this.accessError = error),
    });
  }

  revoke(namespace: string, username: string) {
    this.accessError = "";
    this.teamsService.revokeAccess(namespace, username).subscribe({
      next: () => this.loadAccess(),
      error: (error) => (this.accessError = error),
    });
  }

  loadCompliance() {
    this.teamsService.getComplianceSummaries().subscribe({
      next: (summaries) => {
        this.compliance = {};
        for (const summary of summaries) {
          this.compliance[summary.team_id] = summary;
        }
      },
      // Compliance is supplementary; a failure here must not blank the team list.
      error: (error) => console.error("Failed to load compliance:", error),
    });
  }

  loadApplications() {
    this.teamsService.getApplications().subscribe({
      next: (teamApps) => {
        this.appGroups = {};
        this.appGroupsByNs = {};
        this.teamNamespace = {};
        for (const entry of teamApps) {
          this.appGroups[entry.team_id] = this.groupApplications(entry.applications);
          this.teamNamespace[entry.team_id] = entry.namespace;

          // Partition the team's apps by namespace, then group each namespace's
          // apps by part-of, so each namespace card shows only its own apps.
          const byNs: { [ns: string]: Application[] } = {};
          for (const app of entry.applications) {
            const ns = app.namespace || entry.namespace || "";
            (byNs[ns] = byNs[ns] || []).push(app);
          }
          const grouped: { [ns: string]: ApplicationGroup[] } = {};
          for (const ns of Object.keys(byNs)) {
            grouped[ns] = this.groupApplications(byNs[ns]);
          }
          this.appGroupsByNs[entry.team_id] = grouped;
        }
      },
      error: (error) => console.error("Failed to load applications:", error),
    });
  }

  // Application groups running in a specific namespace of a team.
  appGroupsFor(teamId: string, namespace: string): ApplicationGroup[] {
    return this.appGroupsByNs[teamId]?.[namespace] || [];
  }

  // --- Application (part-of) card collapse + rollups ----------------------
  // Keyed by team:namespace:group, since the same app name can exist in more
  // than one namespace. Like team cards, these start COLLAPSED.
  appGroupCollapsed: { [key: string]: boolean } = {};

  private appGroupKey(teamId: string, namespace: string, group: ApplicationGroup): string {
    return `${teamId}:${namespace}:${group.name}`;
  }

  toggleAppGroup(teamId: string, namespace: string, group: ApplicationGroup) {
    const key = this.appGroupKey(teamId, namespace, group);
    this.appGroupCollapsed[key] = !this.isAppGroupCollapsed(teamId, namespace, group);
  }

  isAppGroupCollapsed(teamId: string, namespace: string, group: ApplicationGroup): boolean {
    return this.appGroupCollapsed[this.appGroupKey(teamId, namespace, group)] !== false;
  }

  // Health of one component: a Rollout reports its own phase; a plain
  // Deployment has none, so derive it from replica readiness.
  private appHealth(app: Application): string {
    if (app.rollout?.phase) {
      return app.rollout.phase;
    }
    if (app.replicas > 0 && app.ready_replicas === app.replicas) {
      return "Healthy";
    }
    if (app.ready_replicas < app.replicas) {
      return "Progressing";
    }
    return "Unknown";
  }

  // Worst-wins rollup across the group's components.
  groupHealth(group: ApplicationGroup): string {
    const phases = group.apps.map((a) => this.appHealth(a));
    for (const bad of ["Degraded", "Progressing", "Paused"]) {
      if (phases.includes(bad)) {
        return bad;
      }
    }
    return phases.length && phases.every((p) => p === "Healthy") ? "Healthy" : "Unknown";
  }

  // Worst-wins compliance rollup: any non-compliant component fails the group.
  groupCompliance(group: ApplicationGroup): ComplianceStatus {
    const statuses = group.apps.map((a) => a.compliance?.status);
    if (statuses.includes("non_compliant")) {
      return "non_compliant";
    }
    return statuses.length && statuses.every((s) => s === "compliant")
      ? "compliant"
      : "unknown";
  }

  groupComplianceLabel(group: ApplicationGroup): string {
    switch (this.groupCompliance(group)) {
      case "compliant":
        return "Compliant";
      case "non_compliant":
        return "Non-compliant";
      default:
        return "Unknown";
    }
  }

  // Group a namespace's workloads into application cards by their
  // app.kubernetes.io/part-of label; anything without one stands on its own.
  private groupApplications(apps: Application[]): ApplicationGroup[] {
    const groups: { [name: string]: Application[] } = {};
    for (const app of apps) {
      const key = app.part_of || app.name;
      (groups[key] = groups[key] || []).push(app);
    }
    return Object.keys(groups)
      .sort()
      .map((name) => ({ name, apps: groups[name].sort((a, b) => a.name.localeCompare(b.name)) }));
  }

  // Repository name of an image ref (no registry host, no tag), e.g.
  // "localhost:5001/demo-api-py:1.0.0" -> "demo-api-py".
  imageName(image: string): string {
    let ref = (image || "").split("@")[0];
    const slash = ref.indexOf("/");
    if (slash > 0) {
      const first = ref.substring(0, slash);
      if (first.includes(".") || first.includes(":") || first === "localhost") {
        ref = ref.substring(slash + 1);
      }
    }
    const lastSlash = ref.lastIndexOf("/");
    const lastSeg = ref.substring(lastSlash + 1);
    const colon = lastSeg.indexOf(":");
    if (colon >= 0) {
      ref = ref.substring(0, lastSlash + 1) + lastSeg.substring(0, colon);
    }
    return ref;
  }

  // Label for an app's external link: API apps point at their docs, everything
  // else at the app's page.
  appLinkLabel(app: Application): string {
    return app.component === "api" ? "API docs" : "Open app";
  }

  // Per-app compliance expand state, keyed by "<teamId>:<appName>".
  appComplianceExpanded: { [key: string]: boolean } = {};

  toggleAppCompliance(teamId: string, app: Application) {
    const key = `${teamId}:${app.name}`;
    this.appComplianceExpanded[key] = !this.appComplianceExpanded[key];
  }

  isAppComplianceExpanded(teamId: string, app: Application): boolean {
    return !!this.appComplianceExpanded[`${teamId}:${app.name}`];
  }

  appStatusLabel(app: Application): string {
    switch (app.compliance?.status) {
      case "compliant":
        return "Compliant";
      case "non_compliant":
        return "Non-compliant";
      default:
        return "Unknown";
    }
  }

  // Link to the team namespace's rollout list in the Argo Rollouts dashboard.
  teamDashboardUrl(teamId: string): string | null {
    const ns = this.teamNamespace[teamId];
    return ns ? `${environment.rolloutsDashboardUrl}/rollouts/${ns}/` : null;
  }

  // Rollout-list link for a specific namespace (each namespace card header).
  nsDashboardUrl(namespace: string): string | null {
    return namespace
      ? `${environment.rolloutsDashboardUrl}/rollouts/${namespace}/`
      : null;
  }

  // Deep link into the Argo Rollouts dashboard for a given app, or null if it's
  // not a Rollout / the namespace is unknown (the dashboard only shows Rollouts).
  rolloutDashboardUrl(app: Application): string | null {
    const ns = app.namespace;
    if (app.kind !== "Rollout" || !ns) {
      return null;
    }
    return `${environment.rolloutsDashboardUrl}/rollouts/rollout/${ns}/${app.name}`;
  }

  toggleDetail(teamId: string) {
    this.expanded[teamId] = !this.expanded[teamId];
    if (this.expanded[teamId] && !this.complianceDetail[teamId]) {
      this.loadingDetail[teamId] = true;
      this.teamsService.getTeamCompliance(teamId).subscribe({
        next: (detail) => {
          this.complianceDetail[teamId] = detail;
          this.loadingDetail[teamId] = false;
        },
        error: (error) => {
          console.error("Failed to load compliance detail:", error);
          this.loadingDetail[teamId] = false;
        },
      });
    }
  }

  statusOf(teamId: string): ComplianceStatus {
    return this.compliance[teamId]?.status ?? "unknown";
  }

  // Tooltip for the collapsed-card badge. Done here (not inline in the template)
  // because the compliance map is empty until the summaries load.
  complianceReason(teamId: string): string {
    return this.compliance[teamId]?.reason || "Namespace policy compliance";
  }

  statusLabel(teamId: string): string {
    switch (this.statusOf(teamId)) {
      case "compliant":
        return "Compliant";
      case "non_compliant":
        return "Non-compliant";
      default:
        return "Unknown";
    }
  }

  deleteTeam(teamId: string, teamName: string) {
    if (confirm(`Are you sure you want to delete team "${teamName}"?`)) {
      this.teamsService.deleteTeam(teamId).subscribe({
        next: () => {
          this.loadTeams();
        },
        error: (error) => {
          this.errorMessage = error;
        },
      });
    }
  }

  formatDate(dateString: string): string {
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
}
