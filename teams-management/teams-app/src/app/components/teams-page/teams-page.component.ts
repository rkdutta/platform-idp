// src/app/components/teams-page/teams-page.component.ts
import { Component, ViewChild } from "@angular/core";
import { AuthService } from "../../services/auth.service";
import { TeamsService } from "../../services/teams.service";
import { TeamListComponent } from "../team-list/team-list.component";

/**
 * The default route: create a team (admins) and browse teams, namespaces and
 * their applications. Managing *who can access what* lives on the Users page —
 * a per-team access panel doesn't scale as the user count grows.
 */
@Component({
  selector: "app-teams-page",
  templateUrl: "./teams-page.component.html",
  styleUrls: ["./teams-page.component.css"],
})
export class TeamsPageComponent {
  @ViewChild("teamList") teamList!: TeamListComponent;

  downloadingKubeconfig = false;
  kubeconfigError = "";

  constructor(
    public authService: AuthService,
    private teamsService: TeamsService,
  ) {}

  /** Fetches the kubeconfig teams-api serves and triggers a browser download.
   *  A plain <a href> can't carry the Authorization header this needs, so this
   *  fetches via HttpClient (auth already attached by AuthInterceptor) and
   *  downloads it as a Blob instead. */
  downloadKubeconfig(): void {
    this.downloadingKubeconfig = true;
    this.kubeconfigError = "";
    this.teamsService.getKubeconfig().subscribe({
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
