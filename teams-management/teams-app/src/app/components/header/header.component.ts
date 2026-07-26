// import { Component, OnInit } from '@angular/core';
// import { AuthService } from '../../services/auth.service';
// import { KeycloakProfile } from 'keycloak-js';
//
// @Component({
//   selector: 'app-header',
//   templateUrl: './header.component.html',
//   styleUrls: ['./header.component.css']
// })
// export class HeaderComponent implements OnInit {
//   userProfile: KeycloakProfile | null = null;
//   isLoggedIn = false;
//   userRoles: string[] = [];
//   isLoading = true;
//
//   constructor(public authService: AuthService) {}
//
//   async ngOnInit() {
//     try {
//       // Ensure auth state is refreshed
//       await this.authService.refreshAuthState();
//
//       this.isLoggedIn = this.authService.isLoggedInSync();
//
//       if (this.isLoggedIn) {
//         try {
//           this.userProfile = await this.authService.loadUserProfile();
//           this.userRoles = this.authService.getUserRoles();
//         } catch (error) {
//           console.error('Failed to load user profile', error);
//         }
//       }
//     } catch (error) {
//       console.error('Failed to initialize auth state', error);
//     } finally {
//       this.isLoading = false;
//     }
//   }
//
//   async login() {
//     try {
//       await this.authService.login();
//     } catch (error) {
//       console.error('Login failed', error);
//     }
//   }
//
//   async logout() {
//     try {
//       await this.authService.logout();
//       this.isLoggedIn = false;
//       this.userProfile = null;
//       this.userRoles = [];
//     } catch (error) {
//       console.error('Logout failed', error);
//     }
//   }
//
//   get canManageProjects(): boolean {
//     return this.authService.hasRole('team-leader') || this.authService.hasRole('admin');
//   }
// }
//

// src/app/components/header/header.component.ts
import {
  Component,
  OnInit,
  HostListener,
  ElementRef,
} from "@angular/core";
import { AuthService } from "../../services/auth.service";
import { ThemeService } from "../../services/theme.service";
import { ProjectsService } from "../../services/projects.service";
import { environment } from "../../../environments/environment";

/** The claims AuthService.getUserInfoFromToken() projects out of the JWT. */
interface TokenUserInfo {
  username?: string;
  email?: string;
  firstName?: string;
  lastName?: string;
  name?: string;
  roles: string[];
}

@Component({
  selector: "app-header",
  templateUrl: "./header.component.html",
  styleUrls: ["./header.component.css"],
})
export class HeaderComponent implements OnInit {
  userProfile: TokenUserInfo | null = null;
  isLoggedIn = false;
  userRoles: string[] = [];
  isLoading = true;

  // Developer-CLI download dropdown in the header.
  cliMenuOpen = false;

  // Argo CD's own RBAC (synced from teams-api's ownership/grants - see
  // _sync_project_groups) decides what each user can actually do there;
  // this is just the link out.
  readonly argocdUrl = environment.argocdUrl;

  // Kubeconfig download (moved here from the Projects page so it's reachable
  // from anywhere, same placement idea as the CLI download).
  downloadingKubeconfig = false;
  kubeconfigError = "";

  constructor(
    public authService: AuthService,
    public themeService: ThemeService,
    private projectsService: ProjectsService,
    private host: ElementRef,
  ) {}

  toggleTheme() {
    this.themeService.toggle();
  }

  toggleCliMenu(event: Event) {
    event.stopPropagation();
    this.cliMenuOpen = !this.cliMenuOpen;
  }

  // Close the dropdown on an outside click or Escape.
  @HostListener("document:click", ["$event"])
  onDocumentClick(event: MouseEvent) {
    if (this.cliMenuOpen && !this.host.nativeElement.contains(event.target)) {
      this.cliMenuOpen = false;
    }
  }

  @HostListener("document:keydown.escape")
  onEscape() {
    this.cliMenuOpen = false;
  }

  async ngOnInit() {
    try {
      // Ensure auth state is refreshed
      await this.authService.refreshAuthState();

      this.isLoggedIn = this.authService.isLoggedInSync();

      if (this.isLoggedIn) {
        // Read the token only once auth is initialized — getTokenSync() is empty
        // until refreshAuthState() has resolved.
        this.userProfile = this.authService.getUserInfoFromToken();
        this.userRoles = this.userProfile?.roles || [];
      }
    } catch (error) {
      console.error("Failed to initialize auth state", error);
    } finally {
      this.isLoading = false;
    }
  }

  /**
   * Name to greet the user with, from the JWT: full `name`, else `given_name`,
   * else the username. The seeded leads share the given name "Team", so the full
   * name is what actually tells teamlead1 and teamlead2 apart.
   */
  get displayName(): string {
    const p = this.userProfile;
    return p?.name || p?.firstName || p?.username || "";
  }

  async login() {
    try {
      await this.authService.login();
    } catch (error) {
      console.error("Login failed", error);
    }
  }

  async logout() {
    try {
      await this.authService.logout();
      this.isLoggedIn = false;
      this.userProfile = null;
      this.userRoles = [];
    } catch (error) {
      console.error("Logout failed", error);
    }
  }

  get canManageProjects(): boolean {
    return (
      this.authService.hasRole("team-leader") ||
      this.authService.hasRole("admin")
    );
  }

  /** Fetches the kubeconfig teams-api serves and triggers a browser download.
   *  A plain <a href> can't carry the Authorization header this needs, so this
   *  fetches via HttpClient (auth already attached by AuthInterceptor) and
   *  downloads it as a Blob instead. Carries no per-user secret — just cluster
   *  info + an exec plugin (kubectl oidc-login) that does its own PKCE login
   *  against Keycloak at kubectl invocation time — so it's open to anyone
   *  logged in, same as before. */
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
