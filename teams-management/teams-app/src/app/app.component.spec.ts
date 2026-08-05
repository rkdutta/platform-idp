import { TestBed } from '@angular/core/testing';
import { NO_ERRORS_SCHEMA } from '@angular/core';
import { of, throwError } from 'rxjs';
import { AppComponent } from './app.component';
import { AuthService } from './services/auth.service';
import { ProjectsService } from './services/projects.service';
import { Me } from './models/project.model';

// NO_ERRORS_SCHEMA: the template references <app-header> and <router-outlet>,
// neither of which this isolated test declares/imports — it only exercises
// AppComponent's own class logic (ngOnInit's auth/permissions bootstrap).
describe('AppComponent', () => {
  let authSpy: jasmine.SpyObj<AuthService>;
  let projectsSpy: jasmine.SpyObj<ProjectsService>;

  beforeEach(async () => {
    authSpy = jasmine.createSpyObj('AuthService', ['refreshAuthState', 'isLoggedInSync', 'setMe', 'login']);
    projectsSpy = jasmine.createSpyObj('ProjectsService', ['getMe']);

    await TestBed.configureTestingModule({
      declarations: [AppComponent],
      schemas: [NO_ERRORS_SCHEMA],
      providers: [
        { provide: AuthService, useValue: authSpy },
        { provide: ProjectsService, useValue: projectsSpy },
      ],
    }).compileComponents();
  });

  it('creates the component', () => {
    authSpy.refreshAuthState.and.resolveTo();
    authSpy.isLoggedInSync.and.returnValue(false);

    const fixture = TestBed.createComponent(AppComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('when not logged in, skips loading permissions and stops the loading spinner', async () => {
    authSpy.refreshAuthState.and.resolveTo();
    authSpy.isLoggedInSync.and.returnValue(false);

    const fixture = TestBed.createComponent(AppComponent);
    await fixture.componentInstance.ngOnInit();

    expect(fixture.componentInstance.isLoggedIn).toBeFalse();
    expect(fixture.componentInstance.isLoading).toBeFalse();
    expect(projectsSpy.getMe).not.toHaveBeenCalled();
  });

  it('when logged in, loads /me and calls setMe with the result', async () => {
    authSpy.refreshAuthState.and.resolveTo();
    authSpy.isLoggedInSync.and.returnValue(true);
    const me = { is_admin: true } as unknown as Me;
    projectsSpy.getMe.and.returnValue(of(me));

    const fixture = TestBed.createComponent(AppComponent);
    await fixture.componentInstance.ngOnInit();

    expect(fixture.componentInstance.isLoggedIn).toBeTrue();
    expect(authSpy.setMe).toHaveBeenCalledWith(me);
    expect(fixture.componentInstance.permissionsError).toBe('');
  });

  it('degrades to read-only with a visible error when /me fails', async () => {
    authSpy.refreshAuthState.and.resolveTo();
    authSpy.isLoggedInSync.and.returnValue(true);
    projectsSpy.getMe.and.returnValue(throwError(() => 'network error'));

    const fixture = TestBed.createComponent(AppComponent);
    await fixture.componentInstance.ngOnInit();

    expect(authSpy.setMe).toHaveBeenCalledWith(null);
    expect(fixture.componentInstance.permissionsError).toContain('Could not load your permissions');
  });
});
