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
