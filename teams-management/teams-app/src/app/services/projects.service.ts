import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { Project, ProjectCreate, SourceRepoInfo, GithubConnection, ComplianceSummary, ComplianceDetail, NamespaceProvisioningStatus, ProjectEvent, PriorityTier, ProjectApplications, UserRef, NamespaceAccess, NamespaceRole, OwnerRef, Me } from '../models/project.model';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

@Injectable({
  providedIn: 'root'
})
export class ProjectsService {
  private apiUrl = environment.apiUrl;

  constructor(
    private http: HttpClient,
    private authService: AuthService
  ) {}

  getProjects(): Observable<Project[]> {
    const url = `${this.apiUrl}/projects`;
    console.log('🔍 Making API call to:', url);
    console.log('🔐 User authenticated:', this.authService.isLoggedIn());

    return this.http.get<Project[]>(url)
      .pipe(catchError(this.handleError));
  }

  createProject(project: ProjectCreate): Observable<Project> {
    const url = `${this.apiUrl}/projects`;
    console.log('📝 Creating project via API:', url);

    return this.http.post<Project>(url, project)
      .pipe(catchError(this.handleError));
  }

  deleteProject(projectId: string): Observable<any> {
    const url = `${this.apiUrl}/projects/${projectId}`;
    console.log('🗑️ Deleting project via API:', url);

    return this.http.delete(url)
      .pipe(catchError(this.handleError));
  }

  getComplianceSummaries(): Observable<ComplianceSummary[]> {
    const url = `${this.apiUrl}/compliance`;
    return this.http.get<ComplianceSummary[]>(url)
      .pipe(catchError(this.handleError));
  }

  getProjectCompliance(projectId: string): Observable<ComplianceDetail> {
    const url = `${this.apiUrl}/projects/${projectId}/compliance`;
    return this.http.get<ComplianceDetail>(url)
      .pipe(catchError(this.handleError));
  }

  getNamespaceStatuses(): Observable<NamespaceProvisioningStatus[]> {
    const url = `${this.apiUrl}/namespace-status`;
    return this.http.get<NamespaceProvisioningStatus[]>(url)
      .pipe(catchError(this.handleError));
  }

  getProjectEvents(projectId: string): Observable<ProjectEvent[]> {
    const url = `${this.apiUrl}/projects/${projectId}/events`;
    return this.http.get<ProjectEvent[]>(url)
      .pipe(catchError(this.handleError));
  }

  getPriorityClasses(): Observable<PriorityTier[]> {
    const url = `${this.apiUrl}/priority-classes`;
    return this.http.get<PriorityTier[]>(url)
      .pipe(catchError(this.handleError));
  }

  getApplications(): Observable<ProjectApplications[]> {
    const url = `${this.apiUrl}/applications`;
    return this.http.get<ProjectApplications[]>(url)
      .pipe(catchError(this.handleError));
  }

  /** Order an extra namespace (team-<name>-<label>) for a project. */
  orderNamespace(projectId: string, label: string): Observable<Project> {
    const url = `${this.apiUrl}/projects/${projectId}/namespaces`;
    return this.http.post<Project>(url, { label })
      .pipe(catchError(this.handleError));
  }

  /** Delete an ordered namespace from a project (not the default namespace). */
  deleteNamespace(projectId: string, namespace: string): Observable<Project> {
    const url = `${this.apiUrl}/projects/${projectId}/namespaces/${namespace}`;
    return this.http.delete<Project>(url)
      .pipe(catchError(this.handleError));
  }

  /** The caller's effective permissions. The API resolves these from its own
   *  database, so this — not the token — is what the UI gates on. */
  getMe(): Observable<Me> {
    const url = `${this.apiUrl}/me`;
    return this.http.get<Me>(url)
      .pipe(catchError(this.handleError));
  }

  /** All Keycloak realm users, for the assignment pickers. */
  getUsers(): Observable<UserRef[]> {
    const url = `${this.apiUrl}/users`;
    return this.http.get<UserRef[]>(url)
      .pipe(catchError(this.handleError));
  }

  /** Namespace -> users+roles, scoped to the caller's owned projects. */
  getAccess(): Observable<NamespaceAccess[]> {
    const url = `${this.apiUrl}/access`;
    return this.http.get<NamespaceAccess[]>(url)
      .pipe(catchError(this.handleError));
  }

  /** Grant a role, or change an existing one — the API upserts, so this single
   *  call covers both "add user" and "change role". */
  setAccess(namespace: string, user_id: string, role: NamespaceRole): Observable<any> {
    const url = `${this.apiUrl}/access`;
    return this.http.post(url, { namespace, user_id, role })
      .pipe(catchError(this.handleError));
  }

  revokeAccess(namespace: string, user_id: string): Observable<any> {
    const url = `${this.apiUrl}/access`;
    // teams-api reads the grant from the request body on DELETE.
    return this.http.request('delete', url, { body: { namespace, user_id } })
      .pipe(catchError(this.handleError));
  }

  /** Project ownership (admin-managed). Owners control their project's namespaces
   *  and who may access them. */
  addOwner(projectId: string, user_id: string): Observable<OwnerRef[]> {
    const url = `${this.apiUrl}/projects/${projectId}/owners`;
    return this.http.post<OwnerRef[]>(url, { user_id })
      .pipe(catchError(this.handleError));
  }

  removeOwner(projectId: string, userId: string): Observable<OwnerRef[]> {
    const url = `${this.apiUrl}/projects/${projectId}/owners/${userId}`;
    return this.http.delete<OwnerRef[]>(url)
      .pipe(catchError(this.handleError));
  }

  /** The project's effective source repos (project repos ∪ the admin global
   *  whitelist), each annotated with origin + GitHub App connection state.
   *  teams-operator reconciles these into the AppProject's sourceRepos. Any
   *  caller in scope may read; only the owner/admin may add or remove one. */
  getSourceRepos(projectId: string): Observable<SourceRepoInfo[]> {
    const url = `${this.apiUrl}/projects/${projectId}/source-repos`;
    return this.http.get<SourceRepoInfo[]>(url)
      .pipe(catchError(this.handleError));
  }

  addSourceRepo(projectId: string, repoUrl: string): Observable<SourceRepoInfo[]> {
    const url = `${this.apiUrl}/projects/${projectId}/source-repos`;
    return this.http.post<SourceRepoInfo[]>(url, { repo_url: repoUrl })
      .pipe(catchError(this.handleError));
  }

  removeSourceRepo(projectId: string, repoUrl: string): Observable<SourceRepoInfo[]> {
    const url = `${this.apiUrl}/projects/${projectId}/source-repos`;
    // teams-api reads the repo to remove from the request body on DELETE.
    return this.http.request<SourceRepoInfo[]>('delete', url, { body: { repo_url: repoUrl } })
      .pipe(catchError(this.handleError));
  }

  /** Admin-curated global whitelist of repos available to every project. Any
   *  authenticated user may read it (project managers pick from it at creation);
   *  only admins may add/remove. */
  getGlobalSourceRepos(): Observable<string[]> {
    const url = `${this.apiUrl}/source-repos/global`;
    return this.http.get<string[]>(url).pipe(catchError(this.handleError));
  }

  addGlobalSourceRepo(repoUrl: string): Observable<string[]> {
    const url = `${this.apiUrl}/source-repos/global`;
    return this.http.post<string[]>(url, { repo_url: repoUrl })
      .pipe(catchError(this.handleError));
  }

  removeGlobalSourceRepo(repoUrl: string): Observable<string[]> {
    const url = `${this.apiUrl}/source-repos/global`;
    return this.http.request<string[]>('delete', url, { body: { repo_url: repoUrl } })
      .pipe(catchError(this.handleError));
  }

  /** Start the "add repos from GitHub" flow: returns the App install/configure
   *  URL (carrying a signed state) to send the user's browser to. `target` is a
   *  project id, or the literal 'global' for the admin whitelist. For a project a
   *  `connectionId` (one of the project's registered connections) is required —
   *  the install goes to that App. The user picks the repos on GitHub; the
   *  operator resolves and adds them. */
  getGithubInstallUrl(target: string, connectionId?: string): Observable<{ install_url: string }> {
    const params = new URLSearchParams({ target });
    if (connectionId) {
      params.set('connection_id', connectionId);
    }
    const url = `${this.apiUrl}/github/install-url?${params.toString()}`;
    return this.http.get<{ install_url: string }>(url).pipe(catchError(this.handleError));
  }

  /** A project's registered GitHub App connections (owner/admin). Includes ones
   *  still mid-registration (status 'pending'). */
  getGithubConnections(projectId: string): Observable<GithubConnection[]> {
    const url = `${this.apiUrl}/projects/${projectId}/github/connections`;
    return this.http.get<GithubConnection[]>(url).pipe(catchError(this.handleError));
  }

  /** Begin registering a NEW GitHub App connection for a project via GitHub's
   *  App-Manifest flow. Returns the GitHub action URL + the manifest JSON to POST
   *  as an auto-submitting form (see project-list's registerConnection). */
  getGithubRegisterUrl(
    projectId: string,
  ): Observable<{ action_url: string; manifest: string; connection_id: string }> {
    const params = new URLSearchParams({ project_id: projectId });
    const url = `${this.apiUrl}/github/register-url?${params.toString()}`;
    return this.http
      .get<{ action_url: string; manifest: string; connection_id: string }>(url)
      .pipe(catchError(this.handleError));
  }

  /** Grant/revoke the `project-manager` realm role (admin-only server-side) —
   *  a project-manager may self-service create projects (POST /projects). */
  grantProjectManager(userId: string): Observable<any> {
    const url = `${this.apiUrl}/users/${userId}/project-manager`;
    return this.http.post(url, {})
      .pipe(catchError(this.handleError));
  }

  revokeProjectManager(userId: string): Observable<any> {
    const url = `${this.apiUrl}/users/${userId}/project-manager`;
    return this.http.delete(url)
      .pipe(catchError(this.handleError));
  }

  /** A ready-to-use kubeconfig (cluster info + an `exec:` stanza that defers
   *  identity to a local `teams-cli login`) — same content for every caller,
   *  see teams-api's GET /kubeconfig. Plain text, not JSON. */
  getKubeconfig(): Observable<string> {
    const url = `${this.apiUrl}/kubeconfig`;
    return this.http.get(url, { responseType: 'text' })
      .pipe(catchError(this.handleError));
  }

  private handleError = (error: HttpErrorResponse) => {
    let errorMessage = 'An error occurred';

    console.error('API Error:', error);

    if (error.status === 401) {
      errorMessage = 'Unauthorized. Please log in again.';
      this.authService.login();
    } else if (error.status === 403) {
      errorMessage = 'Forbidden. You don\'t have permission for this action.';
    } else if (error.error instanceof ErrorEvent) {
      // Client-side error
      errorMessage = error.error.message;
    } else {
      // Server-side error
      errorMessage = error.error?.detail || error.message || `HTTP ${error.status}`;
    }

    return throwError(() => errorMessage);
  };
}
