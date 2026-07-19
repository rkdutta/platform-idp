import { Component, OnInit } from '@angular/core';
import { AuthService } from './services/auth.service';
import { TeamsService } from './services/teams.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit {
  isLoggedIn = false;
  isLoading = true;
  permissionsError = '';

  constructor(
    public authService: AuthService,
    private teamsService: TeamsService,
  ) {}

  async ngOnInit() {
    try {
      // Ensure auth state is properly initialized
      await this.authService.refreshAuthState();
      this.isLoggedIn = this.authService.isLoggedInSync();
      if (this.isLoggedIn) {
        await this.loadPermissions();
      }
    } catch (error) {
      console.error('Failed to initialize app auth state', error);
      this.isLoggedIn = false;
    } finally {
      this.isLoading = false;
    }
  }

  /**
   * Load the caller's effective permissions before rendering any route.
   *
   * Ownership and per-namespace roles are database state in teams-api, so the
   * token can't tell us what this user may do — every role-gated control depends
   * on this. Loading it up front also stops controls flickering into view once
   * the response lands.
   */
  private async loadPermissions(): Promise<void> {
    try {
      const me = await this.teamsService.getMe().toPromise();
      this.authService.setMe(me ?? null);
    } catch (error) {
      // Degrade to read-only rather than blocking the portal; the user still gets
      // the header and a clear reason why nothing is actionable.
      this.authService.setMe(null);
      this.permissionsError =
        `Could not load your permissions (${error}). Showing the portal read-only.`;
    }
  }

  async login() {
    try {
      await this.authService.login();
      this.isLoggedIn = true;
      await this.loadPermissions();
    } catch (error) {
      console.error('Login failed', error);
    }
  }
}
