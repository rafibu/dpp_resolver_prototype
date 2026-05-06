export interface SpawnSpec {
  stack: 'spring-postgres' | 'fastapi-mongo';
  issuer_id: string;
  subject_types: string[];
}

export interface LogLine {
  timestamp: string;
  level: string;
  message: string;
  [key: string]: any;
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

export interface DppSummary {
  dpp_id: string;
  current_version: number;
  subject_type: string;
  last_updated: string;
}

export interface DppRevision {
  version: number;
  schema_ref: string;
  hash: string;
  timestamp: string;
  payload: any;
}

export interface DppDetail {
  dpp_id: string;
  subject_type: string;
  revisions: DppRevision[];
}

export interface IssueRequest {
  dpp_id: string;
  subject_type: string;
  schema_ref: string;
  payload: any;
}

export interface ReviseRequest {
  schema_ref: string;
  payload: any;
}

export interface SchemaInfo {
  subject_type: string;
  major: number;
  minor: number;
  schema: any;
}
