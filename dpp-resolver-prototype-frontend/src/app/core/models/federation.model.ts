export enum PlatformStatus {
  STARTING = 'STARTING',
  RUNNING = 'RUNNING',
  PAUSED = 'PAUSED',
  ERROR = 'ERROR'
}

export interface PlatformInfo {
  platform_id: string;
  stack: string;
  issuer_id: string;
  subject_types: string[];
  external_url: string;
  status: PlatformStatus;
  created_at: string;
}

export interface ResolverInfo {
  external_url: string;
  status: PlatformStatus;
}

export interface FederationOverview {
  resolver: ResolverInfo | null;
  platforms: PlatformInfo[];
}
