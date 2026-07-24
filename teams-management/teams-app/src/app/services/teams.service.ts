import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { Team, TeamCreate, ComplianceSummary, ComplianceDetail, NamespaceProvisioningStatus, TeamEvent, PriorityTier, TeamApplications, UserRef, NamespaceAccess, NamespaceRole, OwnerRef, Me } from '../models/team.model';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

@Injectable({
  providedIn: 'root'
})
export class TeamsService {
  private apiUrl = environment.apiUrl;

  constructor(
    private http: HttpClient,
    private authService: AuthService
  ) {}

  getTeams(): Observable<Team[]> {
    const url = `${this.apiUrl}/teams`;
    console.log('🔍 Making API call to:', url);
    console.log('🔐 User authenticated:', this.authService.isLoggedIn());
    
    return this.http.get<Team[]>(url)
      .pipe(catchError(this.handleError));
  }

  createTeam(team: TeamCreate): Observable<Team> {
    const url = `${this.apiUrl}/teams`;
    console.log('📝 Creating team via API:', url);
    
    return this.http.post<Team>(url, team)
      .pipe(catchError(this.handleError));
  }

  deleteTeam(teamId: string): Observable<any> {
    const url = `${this.apiUrl}/teams/${teamId}`;
    console.log('🗑️ Deleting team via API:', url);

    return this.http.delete(url)
      .pipe(catchError(this.handleError));
  }

  getComplianceSummaries(): Observable<ComplianceSummary[]> {
    const url = `${this.apiUrl}/compliance`;
    return this.http.get<ComplianceSummary[]>(url)
      .pipe(catchError(this.handleError));
  }

  getTeamCompliance(teamId: string): Observable<ComplianceDetail> {
    const url = `${this.apiUrl}/teams/${teamId}/compliance`;
    return this.http.get<ComplianceDetail>(url)
      .pipe(catchError(this.handleError));
  }

  getNamespaceStatuses(): Observable<NamespaceProvisioningStatus[]> {
    const url = `${this.apiUrl}/namespace-status`;
    return this.http.get<NamespaceProvisioningStatus[]>(url)
      .pipe(catchError(this.handleError));
  }

  getTeamEvents(teamId: string): Observable<TeamEvent[]> {
    const url = `${this.apiUrl}/teams/${teamId}/events`;
    return this.http.get<TeamEvent[]>(url)
      .pipe(catchError(this.handleError));
  }

  getPriorityClasses(): Observable<PriorityTier[]> {
    const url = `${this.apiUrl}/priority-classes`;
    return this.http.get<PriorityTier[]>(url)
      .pipe(catchError(this.handleError));
  }

  getApplications(): Observable<TeamApplications[]> {
    const url = `${this.apiUrl}/applications`;
    return this.http.get<TeamApplications[]>(url)
      .pipe(catchError(this.handleError));
  }

  /** Order an extra namespace (team-<name>-<label>) for a team. */
  orderNamespace(teamId: string, label: string): Observable<Team> {
    const url = `${this.apiUrl}/teams/${teamId}/namespaces`;
    return this.http.post<Team>(url, { label })
      .pipe(catchError(this.handleError));
  }

  /** Delete an ordered namespace from a team (not the default namespace). */
  deleteNamespace(teamId: string, namespace: string): Observable<Team> {
    const url = `${this.apiUrl}/teams/${teamId}/namespaces/${namespace}`;
    return this.http.delete<Team>(url)
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

  /** Namespace -> users+roles, scoped to the caller's owned teams. */
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

  /** Team ownership (admin-managed). Owners control their team's namespaces
   *  and who may access them. */
  addOwner(teamId: string, user_id: string): Observable<OwnerRef[]> {
    const url = `${this.apiUrl}/teams/${teamId}/owners`;
    return this.http.post<OwnerRef[]>(url, { user_id })
      .pipe(catchError(this.handleError));
  }

  removeOwner(teamId: string, userId: string): Observable<OwnerRef[]> {
    const url = `${this.apiUrl}/teams/${teamId}/owners/${userId}`;
    return this.http.delete<OwnerRef[]>(url)
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
