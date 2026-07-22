import { Injectable } from "@angular/core";
import { CanActivate, Router, UrlTree } from "@angular/router";
import { AuthService } from "../services/auth.service";

/**
 * Gates /users on admin or team-owner ("teamlead") — everyone else is sent
 * back to /. The header nav link already hides for other users, and the API
 * itself 403s them (authz.require_any_owner), but a direct/bookmarked/hard-
 * refreshed navigation would otherwise still load the page and show nothing
 * but failed-request errors instead of just not getting there.
 *
 * Awaits AuthService.whenMeReady() rather than checking canManage()
 * synchronously: Angular's initial router navigation runs concurrently with
 * AppComponent.ngOnInit() (which is what loads /me), not after it, so a
 * synchronous check here can race ahead of a real owner's permissions
 * loading on a hard refresh and wrongly redirect them.
 */
@Injectable({
  providedIn: "root",
})
export class ManageGuard implements CanActivate {
  constructor(
    private authService: AuthService,
    private router: Router,
  ) {}

  async canActivate(): Promise<boolean | UrlTree> {
    if (!this.authService.isLoggedInSync()) {
      // Not authenticated: let the app's own logged-out view handle it
      // rather than bouncing to "/" first.
      return true;
    }
    await this.authService.whenMeReady();
    return this.authService.canManage() ? true : this.router.parseUrl("/");
  }
}
