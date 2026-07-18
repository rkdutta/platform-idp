import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { Team, TeamCreate, ComplianceSummary, ComplianceDetail, TeamApplications, UserRef, NamespaceAccess } from '../models/team.model';
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

  /** All Keycloak realm users, for the assignment picker. */
  getUsers(): Observable<UserRef[]> {
    const url = `${this.apiUrl}/users`;
    return this.http.get<UserRef[]>(url)
      .pipe(catchError(this.handleError));
  }

  /** Namespace -> users assignments, scoped to the caller's owned teams. */
  getAccess(): Observable<NamespaceAccess[]> {
    const url = `${this.apiUrl}/access`;
    return this.http.get<NamespaceAccess[]>(url)
      .pipe(catchError(this.handleError));
  }

  grantAccess(namespace: string, username: string): Observable<any> {
    const url = `${this.apiUrl}/access`;
    return this.http.post(url, { namespace, username })
      .pipe(catchError(this.handleError));
  }

  revokeAccess(namespace: string, username: string): Observable<any> {
    const url = `${this.apiUrl}/access`;
    // teams-api reads the grant from the request body on DELETE.
    return this.http.request('delete', url, { body: { namespace, username } })
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
