import { Component, OnInit } from "@angular/core";
import { TeamsService } from "../../services/teams.service";
import { environment } from "../../../environments/environment";
import {
  Team,
  ComplianceStatus,
  ComplianceSummary,
  ComplianceDetail,
  Application,
  ApplicationGroup,
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

  constructor(private teamsService: TeamsService) {}

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
      },
      error: (error) => {
        this.errorMessage = error;
        this.isLoading = false;
      },
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
