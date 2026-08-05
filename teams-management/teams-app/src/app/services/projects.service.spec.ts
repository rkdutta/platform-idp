import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ProjectsService } from './projects.service';
import { AuthService } from './auth.service';
import { environment } from '../../environments/environment';
import { Project } from '../models/project.model';

describe('ProjectsService', () => {
  let service: ProjectsService;
  let httpMock: HttpTestingController;
  let authSpy: jasmine.SpyObj<AuthService>;

  beforeEach(() => {
    authSpy = jasmine.createSpyObj('AuthService', ['isLoggedIn', 'login']);
    authSpy.isLoggedIn.and.resolveTo(true);

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [ProjectsService, { provide: AuthService, useValue: authSpy }],
    });
    service = TestBed.inject(ProjectsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('getProjects GETs /projects', () => {
    const mock: Project[] = [
      { id: '1', name: 'demo', created_at: '', namespaces: [], owners: [], default_namespace: null },
    ];

    service.getProjects().subscribe((projects) => expect(projects).toEqual(mock));

    const req = httpMock.expectOne(`${environment.apiUrl}/projects`);
    expect(req.request.method).toBe('GET');
    req.flush(mock);
  });

  it('createProject POSTs the payload to /projects', () => {
    const created: Project = {
      id: '2',
      name: 'newproj',
      created_at: '',
      namespaces: [],
      owners: [],
      default_namespace: null,
    };

    service.createProject({ name: 'newproj', source_repos: [] }).subscribe((p) => expect(p).toEqual(created));

    const req = httpMock.expectOne(`${environment.apiUrl}/projects`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ name: 'newproj', source_repos: [] });
    req.flush(created);
  });

  it('deleteProject DELETEs /projects/{id}', () => {
    service.deleteProject('abc').subscribe();

    const req = httpMock.expectOne(`${environment.apiUrl}/projects/abc`);
    expect(req.request.method).toBe('DELETE');
    req.flush({});
  });

  it('a 401 response redirects to login via handleError', (done) => {
    service.getProjects().subscribe({
      error: (err) => {
        expect(err).toContain('Unauthorized');
        expect(authSpy.login).toHaveBeenCalled();
        done();
      },
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/projects`);
    req.flush('unauthorized', { status: 401, statusText: 'Unauthorized' });
  });

  it('a 403 response surfaces a forbidden message without triggering login', (done) => {
    service.getProjects().subscribe({
      error: (err) => {
        expect(err).toContain('Forbidden');
        expect(authSpy.login).not.toHaveBeenCalled();
        done();
      },
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/projects`);
    req.flush('forbidden', { status: 403, statusText: 'Forbidden' });
  });
});
