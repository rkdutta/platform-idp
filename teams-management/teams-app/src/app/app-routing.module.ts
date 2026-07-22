// src/app/app-routing.module.ts
import { NgModule } from "@angular/core";
import { RouterModule, Routes } from "@angular/router";

import { TeamsPageComponent } from "./components/teams-page/teams-page.component";
import { UsersPageComponent } from "./components/users-page/users-page.component";
import { ManageGuard } from "./guards/manage.guard";

// Deep links work because nginx serves the SPA with `try_files $uri $uri/
// /index.html` (nginx.k8s.conf) and the `teams-ui` Keycloak client's redirect
// URIs are wildcarded, so a post-login redirect back to /users resolves.
const routes: Routes = [
  { path: "", component: TeamsPageComponent },
  { path: "users", component: UsersPageComponent, canActivate: [ManageGuard] },
  { path: "**", redirectTo: "" },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule],
})
export class AppRoutingModule {}
