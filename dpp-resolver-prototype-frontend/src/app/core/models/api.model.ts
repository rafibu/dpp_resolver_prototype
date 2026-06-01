export interface SpawnSpec {
  stack: 'spring-postgres' | 'fastapi-mongo';
  issuer_id: string;
  subject_types: string[];
}

export interface SchemaVersion {
  subject_type: string;
  major_version: number;
  minor_version: number;
}

export interface IssueRequest {
  dpp_id?: string;
  schema_version: SchemaVersion;
  dpp_payload: any;
}

export interface ReviseRequest {
  schema_version: SchemaVersion;
  dpp_payload: any;
}

export interface DppRevision {
  version: number;
  schema_ref: string;
  hash: string;
  timestamp?: string;
  created_at?: string;
  payload: unknown;
}

export interface DppDetail {
  dpp_id: string;
  subject_type: string;
  revisions: DppRevision[];
}

export interface DppRevisionResponse {
  dpp_id: string;
  version: number;
  schema_version: SchemaVersion;
  dpp_payload: unknown;
  payload_hash: string;
  created_at: string;
}

export interface DppSummary {
  dpp_id: string;
  subject_type: string;
  current_version: number;
  last_updated: string;
}

export interface SchemaInfo {
  subject_type: string;
  major: number;
  minor: number;
  schema: unknown;
}

export interface LogLine {
  timestamp: string;
  level: string;
  message: string;
  extra?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ScenarioStatus {
  scenario_id: string;
  status: 'pending' | 'running' | 'passed' | 'failed';
  steps: ScenarioStep[];
  report_md?: string;
}

export interface ScenarioStep {
  name: string;
  status: 'pending' | 'running' | 'passed' | 'failed';
  error?: string;
}

export interface ScenarioResult {
  scenario_id: string;
  report_md: string;
}
