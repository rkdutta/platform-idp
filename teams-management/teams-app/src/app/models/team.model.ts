// src/app/models/team.model.ts
export interface Team {
  id: string;
  name: string;
  created_at: string;
}

export interface TeamCreate {
  name: string;
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
  applications: Application[];
}
