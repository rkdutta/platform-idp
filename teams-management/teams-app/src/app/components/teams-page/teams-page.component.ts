// src/app/components/teams-page/teams-page.component.ts
import { Component, ViewChild } from "@angular/core";
import { AuthService } from "../../services/auth.service";
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

  constructor(public authService: AuthService) {}
}
