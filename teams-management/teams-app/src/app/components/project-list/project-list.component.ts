import { Component, OnInit, OnDestroy } from "@angular/core";
import { ProjectsService } from "../../services/projects.service";
import { AuthService } from "../../services/auth.service";
import { environment } from "../../../environments/environment";
import {
  Project,
  ComplianceStatus,
  ComplianceSummary,
  ComplianceDetail,
  ProvisioningStatus,
  NamespaceProvisioningStatus,
  NamespaceCondition,
  ProjectEvent,
  PriorityTier,
  Application,
  ApplicationGroup,
} from "../../models/project.model";

// Which project cards are expanded, persisted across page refreshes within
// this browser (same localStorage pattern as ThemeService) - otherwise every
// refresh mid-session re-collapses every card, which is a real hassle when
// you're actively working with a project open.
const COLLAPSE_STORAGE_KEY = "teams-portal-expanded-projects";

@Component({
  selector: "app-project-list",
  templateUrl: "./project-list.component.html",
  styleUrls: ["./project-list.component.css"],
})
export class ProjectListComponent implements OnInit, OnDestroy {
  projects: Project[] = [];
  isLoading = true;
  errorMessage = "";

  // Compliance state, keyed by project id.
  compliance: { [projectId: string]: ComplianceSummary } = {};
  complianceDetail: { [projectId: string]: ComplianceDetail } = {};
  expanded: { [projectId: string]: boolean } = {};
  loadingDetail: { [projectId: string]: boolean } = {};

  // Namespace provisioning status (RBAC/image-pull/quota/limits/network-policy/
  // OpenBao access), keyed by project id THEN namespace — a snapshot of
  // teams-operator's last reconcile attempt for each concern, not a live
  // health check (see docs/openbao-spiffe-access.md and provisioning_status.py
  // in teams-api for why: the platform deliberately doesn't watch a namespace
  // for drift after provisioning it, so it never fights a developer's own
  // changes inside their own namespace).
  namespaceStatus: { [projectId: string]: { [namespace: string]: NamespaceProvisioningStatus } } = {};

  // Project activity feed (teams-operator's Events, aggregated across the
  // project's namespaces) — collapsed by default, lazy-loaded on first
  // expand, then auto-refreshed on a timer only while expanded (collapsing
  // stops the poll, so a long-open tab with many projects doesn't keep
  // hitting the API for panels nobody's looking at).
  eventsExpanded: { [projectId: string]: boolean } = {};
  projectEvents: { [projectId: string]: ProjectEvent[] } = {};
  loadingEvents: { [projectId: string]: boolean } = {};
  private eventsPollHandle: { [projectId: string]: ReturnType<typeof setInterval> } = {};
  private static readonly EVENTS_POLL_INTERVAL_MS = 15000;

  // Applications running in each project's namespace, keyed by project id, already
  // grouped by app.kubernetes.io/part-of into application cards.
  appGroups: { [projectId: string]: ApplicationGroup[] } = {};

  // Application groups keyed by project id THEN namespace, so each namespace card
  // renders only the apps running in it.
  appGroupsByNs: { [projectId: string]: { [namespace: string]: ApplicationGroup[] } } = {};

  // Each project's namespace, keyed by project id (for Rollouts dashboard deep links).
  projectNamespace: { [projectId: string]: string | null } = {};

  // Expansion state per project id. Cards start COLLAPSED, so the list stays
  // scannable (each collapsed card still shows its compliance badge); an entry
  // is only present once the user has toggled that card.
  collapsed: { [projectId: string]: boolean } = {};

  // --- Namespace management (ownership management lives on the Users page) ---
  // Per-project "order namespace" label input.
  orderLabel: { [projectId: string]: string } = {};
  actionError = "";

  // Source repos (Argo CD AppProject.spec.sourceRepos, reconciled onto the
  // cluster by teams-operator) — same collapsed-by-default, lazy-loaded-on-first-
  // expand shape as the "Recent activity" events section below. Any caller in
  // scope of the project can view; only an owner/admin (canManageProject) may
  // add/remove one.
  sourceReposExpanded: { [projectId: string]: boolean } = {};
  sourceRepos: { [projectId: string]: string[] } = {};
  loadingSourceRepos: { [projectId: string]: boolean } = {};
  newRepoUrl: { [projectId: string]: string } = {};

  // public so the template can gate the Delete button on manage rights.
  constructor(
    private projectsService: ProjectsService,
    public authService: AuthService,
  ) {
    this.collapsed = this.loadCollapsedState();
  }

  // Which tenant priority tiers exist, for the info popover next to an
  // application card's Tier field. Not per-project (every project shares the
  // same tier catalog) - loaded once, not reloaded on every loadProjects().
  priorityTiers: PriorityTier[] = [];

  ngOnInit() {
    this.loadProjects();
    this.projectsService.getPriorityClasses().subscribe({
      next: (tiers) => (this.priorityTiers = tiers),
      // Supplementary info popover; a failure here must not blank the project list.
      error: (error) => console.error("Failed to load priority tiers:", error),
    });
  }

  loadProjects() {
    this.isLoading = true;
    this.errorMessage = "";
    // Clear any stale banner; the calls below re-set it only if they fail again,
    // so a recovered backend makes the banner disappear.
    this.actionError = "";

    this.projectsService.getProjects().subscribe({
      next: (projects) => {
        this.projects = projects;
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

  toggleCollapse(projectId: string) {
    this.collapsed[projectId] = !this.isCollapsed(projectId);
    this.persistCollapsedState();
  }

  // Default is collapsed: only an explicit `false` counts as expanded.
  isCollapsed(projectId: string): boolean {
    return this.collapsed[projectId] !== false;
  }

  /** Which project ids are explicitly expanded, from localStorage — the
   *  inverse of `collapsed` (which entries are missing/true), so a fresh
   *  browser with nothing stored yet still defaults every card to collapsed. */
  private loadCollapsedState(): { [projectId: string]: boolean } {
    try {
      const raw = localStorage.getItem(COLLAPSE_STORAGE_KEY);
      const expandedIds: string[] = raw ? JSON.parse(raw) : [];
      const collapsed: { [projectId: string]: boolean } = {};
      for (const id of expandedIds) {
        collapsed[id] = false;
      }
      return collapsed;
    } catch {
      // localStorage may be unavailable (private mode), or hold a bad value
      // from an older version of this key — fall back to "everything collapsed"
      // rather than let a stale/corrupt entry break the page.
      return {};
    }
  }

  private persistCollapsedState(): void {
    try {
      const expandedIds = Object.keys(this.collapsed).filter((id) => this.collapsed[id] === false);
      localStorage.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify(expandedIds));
    } catch {
      // localStorage may be unavailable (private mode) — expansion still
      // works for this session, it just won't persist across a refresh.
    }
  }

  // --- Namespace management -------------------------------------------------

  /** True if the caller owns this project (or is an admin) — resolved server-side
   *  and delivered via GET /me, since ownership isn't in the token. */
  canManageProject(project: Project): boolean {
    return (
      this.authService.isAdmin() ||
      !!this.authService.me?.owned_project_ids.includes(project.id)
    );
  }

  orderNamespace(project: Project) {
    const label = (this.orderLabel[project.id] || "").trim();
    if (!label) {
      return;
    }
    this.actionError = "";
    this.projectsService.orderNamespace(project.id, label).subscribe({
      next: () => {
        this.orderLabel[project.id] = "";
        // No token refresh needed: owning the project already grants the new
        // namespace, and the API resolves that from its database on the next call.
        this.loadProjects();
      },
      error: (error) => (this.actionError = error),
    });
  }

  // The default namespace is just informational now — it's deletable like any
  // other. Read from the API's explicit field rather than array position:
  // once the default can be deleted, no namespace is guaranteed to sort first.
  isDefaultNamespace(project: Project, namespace: string): boolean {
    return project.default_namespace === namespace;
  }

  deleteNamespace(project: Project, namespace: string) {
    const message = this.isDefaultNamespace(project, namespace)
      ? `Delete "${namespace}"? It's this project's default namespace — deleting it removes everything running there, and the project will have no namespaces left until a new one is ordered.`
      : `Delete namespace "${namespace}"? This removes the namespace and everything running in it.`;
    if (!confirm(message)) {
      return;
    }
    this.actionError = "";
    this.projectsService.deleteNamespace(project.id, namespace).subscribe({
      next: () => this.loadProjects(),
      error: (error) => (this.actionError = error),
    });
  }

  toggleSourceRepos(projectId: string) {
    this.sourceReposExpanded[projectId] = !this.sourceReposExpanded[projectId];
    if (this.sourceReposExpanded[projectId] && !this.sourceRepos[projectId]) {
      this.loadSourceRepos(projectId);
    }
  }

  private loadSourceRepos(projectId: string) {
    this.loadingSourceRepos[projectId] = true;
    this.projectsService.getSourceRepos(projectId).subscribe({
      next: (repos) => {
        this.sourceRepos[projectId] = repos;
        this.loadingSourceRepos[projectId] = false;
      },
      error: (error) => {
        console.error("Failed to load source repos:", error);
        this.loadingSourceRepos[projectId] = false;
      },
    });
  }

  addSourceRepo(project: Project) {
    const repoUrl = (this.newRepoUrl[project.id] || "").trim();
    if (!repoUrl) {
      return;
    }
    this.actionError = "";
    this.projectsService.addSourceRepo(project.id, repoUrl).subscribe({
      next: (repos) => {
        this.sourceRepos[project.id] = repos;
        this.newRepoUrl[project.id] = "";
      },
      error: (error) => (this.actionError = error),
    });
  }

  removeSourceRepo(project: Project, repoUrl: string) {
    this.actionError = "";
    this.projectsService.removeSourceRepo(project.id, repoUrl).subscribe({
      next: (repos) => (this.sourceRepos[project.id] = repos),
      error: (error) => (this.actionError = error),
    });
  }

  loadCompliance() {
    this.projectsService.getComplianceSummaries().subscribe({
      next: (summaries) => {
        this.compliance = {};
        for (const summary of summaries) {
          this.compliance[summary.project_id] = summary;
        }
      },
      // Compliance is supplementary; a failure here must not blank the project list.
      error: (error) => console.error("Failed to load compliance:", error),
    });
  }

  loadNamespaceStatus() {
    this.projectsService.getNamespaceStatuses().subscribe({
      next: (statuses) => {
        this.namespaceStatus = {};
        for (const s of statuses) {
          (this.namespaceStatus[s.project_id] = this.namespaceStatus[s.project_id] || {})[s.namespace] = s;
        }
      },
      // Same as compliance: supplementary, a failure here must not blank the project list.
      error: (error) => console.error("Failed to load namespace status:", error),
    });
  }

  loadApplications() {
    this.projectsService.getApplications().subscribe({
      next: (projectApps) => {
        this.appGroups = {};
        this.appGroupsByNs = {};
        this.projectNamespace = {};
        for (const entry of projectApps) {
          this.appGroups[entry.project_id] = this.groupApplications(entry.applications);
          this.projectNamespace[entry.project_id] = entry.namespace;

          // Partition the project's apps by namespace, then group each namespace's
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
          this.appGroupsByNs[entry.project_id] = grouped;
        }
      },
      error: (error) => console.error("Failed to load applications:", error),
    });
  }

  // Application groups running in a specific namespace of a project.
  appGroupsFor(projectId: string, namespace: string): ApplicationGroup[] {
    return this.appGroupsByNs[projectId]?.[namespace] || [];
  }

  // --- Application (part-of) card collapse + rollups ----------------------
  // Keyed by project:namespace:group, since the same app name can exist in more
  // than one namespace. Like project cards, these start COLLAPSED.
  appGroupCollapsed: { [key: string]: boolean } = {};

  private appGroupKey(projectId: string, namespace: string, group: ApplicationGroup): string {
    return `${projectId}:${namespace}:${group.name}`;
  }

  toggleAppGroup(projectId: string, namespace: string, group: ApplicationGroup) {
    const key = this.appGroupKey(projectId, namespace, group);
    this.appGroupCollapsed[key] = !this.isAppGroupCollapsed(projectId, namespace, group);
  }

  isAppGroupCollapsed(projectId: string, namespace: string, group: ApplicationGroup): boolean {
    return this.appGroupCollapsed[this.appGroupKey(projectId, namespace, group)] !== false;
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

  // Per-app compliance expand state, keyed by "<projectId>:<appName>".
  appComplianceExpanded: { [key: string]: boolean } = {};

  toggleAppCompliance(projectId: string, app: Application) {
    const key = `${projectId}:${app.name}`;
    this.appComplianceExpanded[key] = !this.appComplianceExpanded[key];
  }

  isAppComplianceExpanded(projectId: string, app: Application): boolean {
    return !!this.appComplianceExpanded[`${projectId}:${app.name}`];
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

  // Link to the project namespace's rollout list in the Argo Rollouts dashboard.
  projectDashboardUrl(projectId: string): string | null {
    const ns = this.projectNamespace[projectId];
    return ns ? `${environment.rolloutsDashboardUrl}/rollouts/${ns}/` : null;
  }

  // Rollout-list link for a specific namespace (each namespace card header).
  nsDashboardUrl(namespace: string): string | null {
    return namespace
      ? `${environment.rolloutsDashboardUrl}/rollouts/${namespace}/`
      : null;
  }

  // Deep link into OpenBao's UI, landing directly on the "create a new
  // secret" form for this namespace's KV path (kv/<namespace>/...), not the
  // list view — a brand-new project has nothing under its path yet, and the
  // list view's empty state reads as a broken/error page ("unable to find
  // secret... try going back to the root"). The create form is always
  // actionable regardless of whether anything exists yet. No trailing slash:
  // confirmed live that OpenBao's create route rejects a path ending in "/"
  // outright ("The secret path may not end in /") rather than treating it as
  // a directory prefix — the bare namespace name is just the pre-filled
  // starting value in an editable field, so the user still has to type a
  // name after it before saving (the ACL policy only grants
  // "kv/data/<namespace>/*", a name *under* the namespace, never the
  // namespace path itself).
  // OpenBao's own OIDC login decides who can actually save anything there —
  // a maintainer/viewer grant on this namespace maps 1:1 to an OpenBao
  // policy via the identity group-alias teams-operator provisions
  // (ensure_openbao_access; see docs/openbao-spiffe-access.md).
  nsOpenbaoUrl(namespace: string): string | null {
    return namespace
      ? `${environment.openbaoUrl}/ui/vault/secrets/kv/create/${namespace}`
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

  toggleEvents(projectId: string) {
    this.eventsExpanded[projectId] = !this.eventsExpanded[projectId];
    if (this.eventsExpanded[projectId]) {
      this.loadEvents(projectId);
      // Clear any stale handle before starting a new one (defensive —
      // toggling shouldn't normally double-arm this, but a leaked interval
      // is a real bug class, not just a cosmetic one).
      this.stopEventsPoll(projectId);
      this.eventsPollHandle[projectId] = setInterval(
        () => this.loadEvents(projectId),
        ProjectListComponent.EVENTS_POLL_INTERVAL_MS
      );
    } else {
      this.stopEventsPoll(projectId);
    }
  }

  private loadEvents(projectId: string) {
    // Only show the loading indicator on the *first* load — a background
    // refresh replacing an already-visible list shouldn't flash "Loading…"
    // over it every 15s.
    if (!this.projectEvents[projectId]) {
      this.loadingEvents[projectId] = true;
    }
    this.projectsService.getProjectEvents(projectId).subscribe({
      next: (events) => {
        this.projectEvents[projectId] = events;
        this.loadingEvents[projectId] = false;
      },
      error: (error) => {
        console.error("Failed to load project events:", error);
        this.loadingEvents[projectId] = false;
      },
    });
  }

  private stopEventsPoll(projectId: string) {
    const handle = this.eventsPollHandle[projectId];
    if (handle) {
      clearInterval(handle);
      delete this.eventsPollHandle[projectId];
    }
  }

  ngOnDestroy() {
    for (const projectId of Object.keys(this.eventsPollHandle)) {
      this.stopEventsPoll(projectId);
    }
  }

  toggleDetail(projectId: string) {
    this.expanded[projectId] = !this.expanded[projectId];
    if (this.expanded[projectId] && !this.complianceDetail[projectId]) {
      this.loadingDetail[projectId] = true;
      this.projectsService.getProjectCompliance(projectId).subscribe({
        next: (detail) => {
          this.complianceDetail[projectId] = detail;
          this.loadingDetail[projectId] = false;
        },
        error: (error) => {
          console.error("Failed to load compliance detail:", error);
          this.loadingDetail[projectId] = false;
        },
      });
    }
  }

  statusOf(projectId: string): ComplianceStatus {
    return this.compliance[projectId]?.status ?? "unknown";
  }

  // Tooltip for the collapsed-card badge. Done here (not inline in the template)
  // because the compliance map is empty until the summaries load.
  complianceReason(projectId: string): string {
    return this.compliance[projectId]?.reason || "Namespace policy compliance";
  }

  statusLabel(projectId: string): string {
    switch (this.statusOf(projectId)) {
      case "compliant":
        return "Compliant";
      case "non_compliant":
        return "Non-compliant";
      default:
        return "Unknown";
    }
  }

  nsStatusOf(projectId: string, namespace: string): ProvisioningStatus {
    return this.namespaceStatus[projectId]?.[namespace]?.status ?? "unknown";
  }

  nsStatusLabel(projectId: string, namespace: string): string {
    switch (this.nsStatusOf(projectId, namespace)) {
      case "ready":
        return "Ready";
      case "degraded":
        return "Degraded";
      default:
        return "Unknown";
    }
  }

  // Glyph for the status indicator — green tick (success), red cross
  // (failed), yellow light/dot (still being provisioned — "unknown" means
  // teams-operator hasn't reconciled this namespace yet, which reads as
  // "in progress" rather than a real failure).
  nsStatusIcon(projectId: string, namespace: string): string {
    switch (this.nsStatusOf(projectId, namespace)) {
      case "ready":
        return "✓";
      case "degraded":
        return "✗";
      default:
        return "●";
    }
  }

  // Fallback native title="" text, used only when there's no conditions list
  // to show in the hover popover (the "unknown" case — e.g. the operator
  // hasn't reconciled this namespace yet — where there's nothing to list).
  nsStatusReason(projectId: string, namespace: string): string {
    return this.namespaceStatus[projectId]?.[namespace]?.reason || "Namespace provisioning status";
  }

  nsConditions(projectId: string, namespace: string): NamespaceCondition[] {
    return this.namespaceStatus[projectId]?.[namespace]?.conditions ?? [];
  }

  // Plain-English label for each condition `type` teams-operator provisions
  // (see update_namespace_status in teams_operator.py) — the raw type
  // strings are stable identifiers shared with the backend/operator, not
  // meant to be read directly by a project lead.
  private static readonly CONDITION_LABELS: { [type: string]: string } = {
    RBAC: "Project member access (view/edit permissions)",
    ImagePullAccess: "Container image pulls (Harbor)",
    ResourceQuota: "Resource quotas",
    LimitRange: "Default resource limits",
    NetworkPolicy: "Network isolation",
    OpenBaoAccess: "Secrets access (OpenBao)",
  };

  conditionLabel(type: string): string {
    return ProjectListComponent.CONDITION_LABELS[type] || type;
  }

  deleteProject(projectId: string, projectName: string) {
    if (confirm(`Are you sure you want to delete project "${projectName}"?`)) {
      this.projectsService.deleteProject(projectId).subscribe({
        next: () => {
          this.loadProjects();
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
