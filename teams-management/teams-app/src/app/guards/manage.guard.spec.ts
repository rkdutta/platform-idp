import { TestBed } from '@angular/core/testing';
import { Router, UrlTree } from '@angular/router';
import { ManageGuard } from './manage.guard';
import { AuthService } from '../services/auth.service';

describe('ManageGuard', () => {
  let guard: ManageGuard;
  let authSpy: jasmine.SpyObj<AuthService>;
  let router: Router;

  beforeEach(() => {
    authSpy = jasmine.createSpyObj('AuthService', ['isLoggedInSync', 'whenMeReady', 'canManage']);

    TestBed.configureTestingModule({
      providers: [ManageGuard, { provide: AuthService, useValue: authSpy }],
    });
    guard = TestBed.inject(ManageGuard);
    router = TestBed.inject(Router);
  });

  it('allows navigation through when the user is not logged in (lets the logged-out view handle it)', async () => {
    authSpy.isLoggedInSync.and.returnValue(false);

    expect(await guard.canActivate()).toBeTrue();
    expect(authSpy.whenMeReady).not.toHaveBeenCalled();
  });

  it('awaits whenMeReady, then allows a user who canManage()', async () => {
    authSpy.isLoggedInSync.and.returnValue(true);
    authSpy.whenMeReady.and.resolveTo();
    authSpy.canManage.and.returnValue(true);

    expect(await guard.canActivate()).toBeTrue();
    expect(authSpy.whenMeReady).toHaveBeenCalled();
  });

  it('redirects a logged-in user who cannot manage anything back to /', async () => {
    authSpy.isLoggedInSync.and.returnValue(true);
    authSpy.whenMeReady.and.resolveTo();
    authSpy.canManage.and.returnValue(false);

    const result = await guard.canActivate();

    expect(result).not.toBeTrue();
    expect((result as UrlTree).toString()).toBe(router.parseUrl('/').toString());
  });
});
