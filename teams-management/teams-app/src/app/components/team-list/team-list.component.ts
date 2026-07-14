import { Component, OnInit } from "@angular/core";
import { TeamsService } from "../../services/teams.service";
import {
  Team,
  ComplianceStatus,
  ComplianceSummary,
  ComplianceDetail,
  Application,
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

  // Applications running in each team's namespace, keyed by team id.
  applications: { [teamId: string]: Application[] } = {};

  // Rollout action state, keyed by "<teamId>/<appName>".
  deployTag: { [key: string]: string } = {};
  actionBusy: { [key: string]: boolean } = {};
  actionMsg: { [key: string]: string } = {};
  actionError: { [key: string]: boolean } = {};

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
        this.applications = {};
        for (const entry of teamApps) {
          this.applications[entry.team_id] = entry.applications;
        }
      },
      error: (error) => console.error("Failed to load applications:", error),
    });
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

  // Blue/green actions --------------------------------------------------

  actionKey(teamId: string, appName: string): string {
    return `${teamId}/${appName}`;
  }

  promote(teamId: string, app: Application) {
    const key = this.actionKey(teamId, app.name);
    const preview = app.rollout?.preview_version ?? "the preview version";
    if (!confirm(`Promote ${app.name} to ${preview}? This flips live traffic.`)) {
      return;
    }
    this.runAction(key, this.teamsService.promoteApp(teamId, app.name),
      `Promoting ${app.name}…`, `Promoted ${app.name}`);
  }

  deploy(teamId: string, app: Application) {
    const key = this.actionKey(teamId, app.name);
    const tag = (this.deployTag[key] || "").trim();
    if (!tag) {
      this.setMsg(key, "Enter an image tag first", true);
      return;
    }
    if (!confirm(`Deploy ${app.name}:${tag} as a new preview (green)?`)) {
      return;
    }
    this.runAction(key, this.teamsService.setAppImage(teamId, app.name, tag),
      `Deploying ${app.name}:${tag}…`, `Started rollout of ${app.name}:${tag}`);
  }

  discard(teamId: string, app: Application) {
    const key = this.actionKey(teamId, app.name);
    const preview = app.rollout?.preview_version ?? "the preview";
    const active = app.rollout?.active_version ?? "the active version";
    if (!confirm(`Discard preview ${preview} and keep ${active} live?`)) {
      return;
    }
    this.runAction(key, this.teamsService.discardAppPreview(teamId, app.name),
      `Discarding preview of ${app.name}…`, `Discarded preview of ${app.name}`);
  }

  private runAction(key: string, obs: any, pending: string, success: string) {
    this.actionBusy[key] = true;
    this.setMsg(key, pending, false);
    obs.subscribe({
      next: () => {
        this.actionBusy[key] = false;
        this.setMsg(key, success, false);
        this.deployTag[key] = "";
        // Let the rollout controller react, then refresh status.
        setTimeout(() => this.loadApplications(), 1500);
      },
      error: (error: any) => {
        this.actionBusy[key] = false;
        this.setMsg(key, typeof error === "string" ? error : "Action failed", true);
      },
    });
  }

  private setMsg(key: string, msg: string, isError: boolean) {
    this.actionMsg[key] = msg;
    this.actionError[key] = isError;
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
