// src/app/components/projects-page/projects-page.component.ts
import { Component, ViewChild } from "@angular/core";
import { AuthService } from "../../services/auth.service";
import { ProjectsService } from "../../services/projects.service";
import { ProjectListComponent } from "../project-list/project-list.component";

/**
 * The default route: create a project (admins) and browse projects, namespaces and
 * their applications. Managing *who can access what* lives on the Users page —
 * a per-project access panel doesn't scale as the user count grows.
 */
@Component({
  selector: "app-projects-page",
  templateUrl: "./projects-page.component.html",
  styleUrls: ["./projects-page.component.css"],
})
export class ProjectsPageComponent {
  @ViewChild("projectList") projectList!: ProjectListComponent;

  downloadingKubeconfig = false;
  kubeconfigError = "";

  constructor(
    public authService: AuthService,
    private projectsService: ProjectsService,
  ) {}

  /** Fetches the kubeconfig teams-api serves and triggers a browser download.
   *  A plain <a href> can't carry the Authorization header this needs, so this
   *  fetches via HttpClient (auth already attached by AuthInterceptor) and
   *  downloads it as a Blob instead. */
  downloadKubeconfig(): void {
    this.downloadingKubeconfig = true;
    this.kubeconfigError = "";
    this.projectsService.getKubeconfig().subscribe({
      next: (yaml) => {
        this.downloadingKubeconfig = false;
        const blob = new Blob([yaml], { type: "application/yaml" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "teams-kubeconfig.yaml";
        a.click();
        URL.revokeObjectURL(url);
      },
      error: (err) => {
        this.downloadingKubeconfig = false;
        this.kubeconfigError = `Could not fetch kubeconfig: ${err}`;
      },
    });
  }
}
