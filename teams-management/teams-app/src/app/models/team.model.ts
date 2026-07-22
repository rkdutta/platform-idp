// src/app/models/team.model.ts

/** A user's role *within a single namespace*. Ownership of the team implies
 *  `maintainer` on all of its namespaces (the API derives that). */
export type NamespaceRole = 'viewer' | 'maintainer';

export interface OwnerRef {
  user_id: string;
  username: string;
}

export interface Team {
  id: string;
  name: string;
  created_at: string;
  namespaces: string[];
  owners: OwnerRef[];
  default_namespace: string | null;
}

export interface TeamCreate {
  name: string;
}

/** A Keycloak realm user (the directory the pickers are populated from). */
export interface UserRef {
  id: string; // Keycloak `sub` — what grants are keyed on
  username: string;
  firstName: string;
  lastName: string;
  email: string;
  roles: string[]; // realm roles; only `admin` still carries authority
}

export interface AccessUser {
  user_id: string;
  username: string;
  role: NamespaceRole;
  via: 'owner' | 'grant'; // implicit (team ownership) vs an explicit per-namespace grant
}

/** Which users hold which role in a namespace (scoped to teams the caller owns). */
export interface NamespaceAccess {
  namespace: string;
  team_id: string;
  team_name: string;
  users: AccessUser[];
}

/** The caller's effective permissions, resolved server-side.
 *
 *  Authority lives in the API database now, so the UI can't infer it from token
 *  roles — everything role-gated reads from here. */
export interface Me {
  user_id: string;
  username: string;
  is_admin: boolean;
  owned_team_ids: string[];
  namespaces: { namespace: string; role: NamespaceRole }[];
}

export type ComplianceStatus = 'compliant' | 'non_compliant' | 'unknown';

export interface PolicyResult {
  name: string;
  kind: string;
  enforcement_action: string;
  compliant: boolean;
  violation_count: number;
  messages: string[];
}

export interface ComplianceSummary {
  team_id: string;
  team_name: string;
  namespace: string | null;
  status: ComplianceStatus;
  reason?: string | null;
  failing_policies: number;
  total_policies: number;
  checked_at: string;
}

export interface ComplianceDetail extends ComplianceSummary {
  policies: PolicyResult[];
}

export interface RolloutStatus {
  strategy: string; // BlueGreen | Canary | Unknown
  phase: string; // Healthy | Paused | Progressing | Degraded ...
  message: string;
  active_version: string | null;
  preview_version: string | null;
  awaiting_promotion: boolean;
}

export interface AppPolicyResult {
  id: string;
  name: string;
  category: string; // supply-chain | gatekeeper
  compliant: boolean;
  detail?: string;
  kind?: string | null;
  enforcement_action?: string | null;
  messages?: string[];
}

export interface AppCompliance {
  status: ComplianceStatus; // compliant | non_compliant | unknown
  reason?: string | null;
  total_policies: number;
  failing_policies: number;
  policies: AppPolicyResult[];
}

export interface Application {
  name: string;
  namespace?: string | null; // which team namespace this app runs in
  version: string;
  kind: string; // Rollout | Deployment
  image: string;
  replicas: number;
  ready_replicas: number;
  part_of?: string | null; // app.kubernetes.io/part-of (grouping key)
  component?: string | null; // app.kubernetes.io/component (web | api)
  url?: string | null; // browser URL: web -> page, api -> Swagger docs
  compliance?: AppCompliance | null;
  rollout?: RolloutStatus | null;
}

export interface ApplicationGroup {
  name: string;
  apps: Application[];
}

export interface TeamApplications {
  team_id: string;
  team_name: string;
  namespace: string | null;
  namespaces?: string[];
  applications: Application[];
}
