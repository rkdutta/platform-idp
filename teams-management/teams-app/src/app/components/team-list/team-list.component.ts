import { Component, OnInit } from "@angular/core";
import { TeamsService } from "../../services/teams.service";
import { AuthService } from "../../services/auth.service";
import { environment } from "../../../environments/environment";
import {
  Team,
  ComplianceStatus,
  ComplianceSummary,
  ComplianceDetail,
  ProvisioningStatus,
  NamespaceProvisioningStatus,
  NamespaceCondition,
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

  // Namespace provisioning status (RBAC/image-pull/quota/limits/network-policy/
  // OpenBao access), keyed by team id THEN namespace — a snapshot of
  // teams-operator's last reconcile attempt for each concern, not a live
  // health check (see docs/openbao-spiffe-access.md and provisioning_status.py
  // in teams-api for why: the platform deliberately doesn't watch a namespace
  // for drift after provisioning it, so it never fights a developer's own
  // changes inside their own namespace).
  namespaceStatus: { [teamId: string]: { [namespace: string]: NamespaceProvisioningStatus } } = {};

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

  // --- Namespace management (ownership management lives on the Users page) ---
  // Per-team "order namespace" label input.
  orderLabel: { [teamId: string]: string } = {};
  actionError = "";

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
    // Clear any stale banner; the calls below re-set it only if they fail again,
    // so a recovered backend makes the banner disappear.
    this.actionError = "";

    this.teamsService.getTeams().subscribe({
      next: (teams) => {
        this.teams = teams;
        this.isLoading = false;
        this.loadCompliance();
        this.loadApplications();
        this.loadNamespaceStatus();
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

  // --- Namespace management -------------------------------------------------

  /** True if the caller owns this team (or is an admin) — resolved server-side
   *  and delivered via GET /me, since ownership isn't in the token. */
  canManageTeam(team: Team): boolean {
    return (
      this.authService.isAdmin() ||
      !!this.authService.me?.owned_team_ids.includes(team.id)
    );
  }

  orderNamespace(team: Team) {
    const label = (this.orderLabel[team.id] || "").trim();
    if (!label) {
      return;
    }
    this.actionError = "";
    this.teamsService.orderNamespace(team.id, label).subscribe({
      next: () => {
        this.orderLabel[team.id] = "";
        // No token refresh needed: owning the team already grants the new
        // namespace, and the API resolves that from its database on the next call.
        this.loadTeams();
      },
      error: (error) => (this.actionError = error),
    });
  }

  // The default namespace is just informational now — it's deletable like any
  // other. Read from the API's explicit field rather than array position:
  // once the default can be deleted, no namespace is guaranteed to sort first.
  isDefaultNamespace(team: Team, namespace: string): boolean {
    return team.default_namespace === namespace;
  }

  deleteNamespace(team: Team, namespace: string) {
    const message = this.isDefaultNamespace(team, namespace)
      ? `Delete "${namespace}"? It's this team's default namespace — deleting it removes everything running there, and the team will have no namespaces left until a new one is ordered.`
      : `Delete namespace "${namespace}"? This removes the namespace and everything running in it.`;
    if (!confirm(message)) {
      return;
    }
    this.actionError = "";
    this.teamsService.deleteNamespace(team.id, namespace).subscribe({
      next: () => this.loadTeams(),
      error: (error) => (this.actionError = error),
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

  loadNamespaceStatus() {
    this.teamsService.getNamespaceStatuses().subscribe({
      next: (statuses) => {
        this.namespaceStatus = {};
        for (const s of statuses) {
          (this.namespaceStatus[s.team_id] = this.namespaceStatus[s.team_id] || {})[s.namespace] = s;
        }
      },
      // Same as compliance: supplementary, a failure here must not blank the team list.
      error: (error) => console.error("Failed to load namespace status:", error),
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

  nsStatusOf(teamId: string, namespace: string): ProvisioningStatus {
    return this.namespaceStatus[teamId]?.[namespace]?.status ?? "unknown";
  }

  nsStatusLabel(teamId: string, namespace: string): string {
    switch (this.nsStatusOf(teamId, namespace)) {
      case "ready":
        return "Ready";
      case "degraded":
        return "Degraded";
      default:
        return "Unknown";
    }
  }

  // Fallback native title="" text, used only when there's no conditions list
  // to show in the hover popover (the "unknown" case — e.g. the operator
  // hasn't reconciled this namespace yet — where there's nothing to list).
  nsStatusReason(teamId: string, namespace: string): string {
    return this.namespaceStatus[teamId]?.[namespace]?.reason || "Namespace provisioning status";
  }

  nsConditions(teamId: string, namespace: string): NamespaceCondition[] {
    return this.namespaceStatus[teamId]?.[namespace]?.conditions ?? [];
  }

  // Plain-English label for each condition `type` teams-operator provisions
  // (see update_namespace_status in teams_operator.py) — the raw type
  // strings are stable identifiers shared with the backend/operator, not
  // meant to be read directly by a team lead.
  private static readonly CONDITION_LABELS: { [type: string]: string } = {
    RBAC: "Team member access (view/edit permissions)",
    ImagePullAccess: "Container image pulls (Harbor)",
    ResourceQuota: "Resource quotas",
    LimitRange: "Default resource limits",
    NetworkPolicy: "Network isolation",
    OpenBaoAccess: "Secrets access (OpenBao)",
  };

  conditionLabel(type: string): string {
    return TeamListComponent.CONDITION_LABELS[type] || type;
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
