import { TestBed } from '@angular/core/testing';
import { KeycloakService } from 'keycloak-angular';
import { AuthService } from './auth.service';
import { Me } from '../models/project.model';

describe('AuthService', () => {
  let service: AuthService;
  let keycloakSpy: jasmine.SpyObj<KeycloakService>;

  beforeEach(() => {
    keycloakSpy = jasmine.createSpyObj('KeycloakService', [
      'isLoggedIn',
      'updateToken',
      'getToken',
      'login',
      'logout',
      'isUserInRole',
      'getUserRoles',
      'loadUserProfile',
    ]);
    // AuthService's constructor calls initializeAuth() -> isLoggedIn() ->
    // (if true) updateToken()/getToken() — all must resolve or the
    // fire-and-forget async call rejects unhandled.
    keycloakSpy.isLoggedIn.and.resolveTo(false);
    keycloakSpy.updateToken.and.resolveTo(false);
    keycloakSpy.getToken.and.resolveTo('');

    TestBed.configureTestingModule({
      providers: [AuthService, { provide: KeycloakService, useValue: keycloakSpy }],
    });
    service = TestBed.inject(AuthService);
  });

  it('is created', () => {
    expect(service).toBeTruthy();
  });

  it('reports not-manage/not-admin/not-project-manager before setMe is called', () => {
    expect(service.isAdmin()).toBeFalse();
    expect(service.canManage()).toBeFalse();
    expect(service.isProjectManager()).toBeFalse();
  });

  it('isAdmin/canManage/isProjectManager reflect the last setMe() call', () => {
    const me: Me = {
      user_id: 'u1',
      username: 'admin',
      is_admin: true,
      is_project_manager: false,
      owned_project_ids: [],
      namespaces: [],
    } as unknown as Me;

    service.setMe(me);

    expect(service.isAdmin()).toBeTrue();
    expect(service.canManage()).toBeTrue(); // admin implies canManage
  });

  it('canManage is true for a non-admin who owns at least one project', () => {
    const me: Me = {
      user_id: 'u2',
      username: 'teamlead1',
      is_admin: false,
      is_project_manager: true,
      owned_project_ids: ['p1'],
      namespaces: [],
    } as unknown as Me;

    service.setMe(me);

    expect(service.isAdmin()).toBeFalse();
    expect(service.canManage()).toBeTrue();
    expect(service.isProjectManager()).toBeTrue();
  });

  it('roleIn returns the role for a namespace the user has access to, else null', () => {
    const me: Me = {
      user_id: 'u3',
      username: 'viewer1',
      is_admin: false,
      is_project_manager: false,
      owned_project_ids: [],
      namespaces: [{ namespace: 'project-demo-default', role: 'viewer' }],
    } as unknown as Me;

    service.setMe(me);

    expect(service.roleIn('project-demo-default')).toBe('viewer' as any);
    expect(service.roleIn('project-unrelated-default')).toBeNull();
  });

  it('whenMeReady resolves once setMe has been called', async () => {
    let resolved = false;
    service.whenMeReady().then(() => (resolved = true));

    expect(resolved).toBeFalse();
    service.setMe(null);
    await service.whenMeReady();

    expect(resolved).toBeTrue();
  });

  it('logout clears login state, token, and cached permissions', async () => {
    keycloakSpy.logout.and.resolveTo();
    service.setMe({ is_admin: true } as unknown as Me);

    await service.logout();

    expect(service.isLoggedInSync()).toBeFalse();
    expect(service.getTokenSync()).toBe('');
    expect(service.me).toBeNull();
  });

  it('hasRole delegates to keycloak.isUserInRole and swallows errors', () => {
    keycloakSpy.isUserInRole.and.returnValue(true);
    expect(service.hasRole('admin')).toBeTrue();

    keycloakSpy.isUserInRole.and.throwError('not initialized');
    expect(service.hasRole('admin')).toBeFalse();
  });
});
