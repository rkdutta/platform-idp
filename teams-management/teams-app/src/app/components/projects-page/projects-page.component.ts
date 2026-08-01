// src/app/components/projects-page/projects-page.component.ts
import { Component, ViewChild } from "@angular/core";
import { AuthService } from "../../services/auth.service";
import { ProjectListComponent } from "../project-list/project-list.component";

/**
 * The default route: create a project (admins / project managers) and browse
 * projects, namespaces and their applications. Managing *who can access what*
 * lives on the Users page — a per-project access panel doesn't scale as the
 * user count grows. Source repos are managed per-project from each project's
 * card (register a GitHub connection); see docs/self-service-repos-github-app.md.
 */
@Component({
  selector: "app-projects-page",
  templateUrl: "./projects-page.component.html",
  styleUrls: ["./projects-page.component.css"],
})
export class ProjectsPageComponent {
  @ViewChild("projectList") projectList!: ProjectListComponent;

  constructor(public authService: AuthService) {}
}
