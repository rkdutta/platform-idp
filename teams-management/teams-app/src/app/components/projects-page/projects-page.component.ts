// src/app/components/projects-page/projects-page.component.ts
import { Component, OnInit, ViewChild } from "@angular/core";
import { AuthService } from "../../services/auth.service";
import { ProjectsService } from "../../services/projects.service";
import { ProjectListComponent } from "../project-list/project-list.component";

/**
 * The default route: create a project (admins) and browse projects, namespaces and
 * their applications. Managing *who can access what* lives on the Users page —
 * a per-project access panel doesn't scale as the user count grows.
 *
 * Admins also curate the global source-repo whitelist here (repos every project
 * may use); see docs/self-service-repos-github-app.md.
 */
@Component({
  selector: "app-projects-page",
  templateUrl: "./projects-page.component.html",
  styleUrls: ["./projects-page.component.css"],
})
export class ProjectsPageComponent implements OnInit {
  @ViewChild("projectList") projectList!: ProjectListComponent;

  globalRepos: string[] = [];
  globalReposError = "";

  constructor(
    public authService: AuthService,
    private projectsService: ProjectsService,
  ) {}

  ngOnInit() {
    // Only admins manage the whitelist; load it only where the panel is shown.
    if (this.authService.isAdmin()) {
      this.loadGlobalRepos();
    }
  }

  private loadGlobalRepos() {
    this.projectsService.getGlobalSourceRepos().subscribe({
      next: (repos) => (this.globalRepos = repos),
      error: (err) => (this.globalReposError = err),
    });
  }

  /** "Add repos from GitHub" for the global whitelist: send the browser to the
   *  GitHub App to pick repositories; the operator resolves and adds them. */
  addReposFromGithub() {
    this.globalReposError = "";
    this.projectsService.getGithubInstallUrl("global").subscribe({
      next: (res) => (window.location.href = res.install_url),
      error: (err) => (this.globalReposError = err),
    });
  }

  removeGlobalRepo(url: string) {
    this.globalReposError = "";
    this.projectsService.removeGlobalSourceRepo(url).subscribe({
      next: (repos) => (this.globalRepos = repos),
      error: (err) => (this.globalReposError = err),
    });
  }

  /** Compact chip label for a repo URL — "owner/repo", host+".git" stripped.
   *  The full URL stays available via the chip's title on hover. */
  shortRepo(url: string): string {
    try {
      const u = new URL(url);
      return u.pathname.replace(/^\/+/, "").replace(/\.git$/, "") || u.hostname;
    } catch {
      return url.replace(/^https?:\/\//, "").replace(/\.git$/, "");
    }
  }
}
