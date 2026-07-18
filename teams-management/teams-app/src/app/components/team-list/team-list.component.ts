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

  // Each team's namespace, keyed by team id (for Rollouts dashboard deep links).
  teamNamespace: { [teamId: string]: string | null } = {};

  // Collapsed team cards, keyed by team id. Cards start expanded.
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
    this.collapsed[teamId] = !this.collapsed[teamId];
  }

  isCollapsed(teamId: string): boolean {
    return !!this.collapsed[teamId];
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
      error: (error) => console.error("Failed to load users:", error),
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

  orderNamespace(team: Team) {
    const label = (this.orderLabel[team.id] || "").trim();
    if (!label) {
      return;
    }
    this.accessError = "";
    this.teamsService.orderNamespace(team.id, label).subscribe({
      next: () => {
        this.orderLabel[team.id] = "";
        this.loadTeams(); // refresh namespaces + access
      },
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
        this.teamNamespace = {};
        for (const entry of teamApps) {
          this.appGroups[entry.team_id] = this.groupApplications(entry.applications);
          this.teamNamespace[entry.team_id] = entry.namespace;
        }
      },
      error: (error) => console.error("Failed to load applications:", error),
    });
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

  // Deep link into the Argo Rollouts dashboard for a given app, or null if it's
  // not a Rollout / the namespace is unknown (the dashboard only shows Rollouts).
  rolloutDashboardUrl(teamId: string, app: Application): string | null {
    const ns = this.teamNamespace[teamId];
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
