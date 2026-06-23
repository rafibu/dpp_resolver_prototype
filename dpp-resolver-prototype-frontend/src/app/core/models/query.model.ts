/**
 * Query models for platform-local predicate and reverse-traverse queries.
 *
 * These shapes mirror the Java platform DTOs in
 * `generic_dpp_platform_java/.../queries/dtos`:
 *  - {@link PredicateQueryRequest} mirrors `PredicateQueryRequestDTO`
 *  - {@link TraverseQueryRequest} mirrors the flattened `TraverseQueryRequestDTO`
 *    (subject_type / dpp_id live directly on the request, never inside a nested
 *    target object).
 *
 * The conceptual request objects below use snake_case field names so the live
 * JSON preview matches the documented contract. The actual wire format is GET
 * query parameters (camelCase, indexed) produced by `QueryService`; see
 * `dpp-workload-generator/src/workload/clients.py` for the reference encoder.
 */

/** Mirrors Java `QueryResultMode`. */
export enum QueryResultMode {
  SELECT = 'SELECT',
  COUNT = 'COUNT',
  SUM = 'SUM'
}

/** Mirrors Java `QueryExecutionMode`. Defaults to INDEXED. */
export enum QueryExecutionMode {
  INDEXED = 'INDEXED',
  ON_DEMAND = 'ON_DEMAND'
}

/** Mirrors Java `PredicateOperator` exactly. */
export enum PredicateOperator {
  EQ = 'EQ',
  NEQ = 'NEQ',
  EXISTS = 'EXISTS',
  NOT_EXISTS = 'NOT_EXISTS',
  IN = 'IN',
  GT = 'GT',
  GTE = 'GTE',
  LT = 'LT',
  LTE = 'LTE'
}

/** Operators that ignore the filter value (Java reads the projected fact only). */
export const VALUE_LESS_OPERATORS: ReadonlySet<PredicateOperator> = new Set([
  PredicateOperator.EXISTS,
  PredicateOperator.NOT_EXISTS
]);

/** Operators that take a list of candidate values. */
export const LIST_OPERATORS: ReadonlySet<PredicateOperator> = new Set([PredicateOperator.IN]);

/** Conceptual predicate filter (mirrors `PredicateFilterDTO`). */
export interface PredicateFilter {
  path: string;
  operator: PredicateOperator;
  /** Omitted for EXISTS / NOT_EXISTS. A list for IN. */
  value?: unknown;
}

/** Conceptual predicate request (mirrors `PredicateQueryRequestDTO`). */
export interface PredicateQueryRequest {
  result_mode: QueryResultMode;
  execution_mode: QueryExecutionMode;
  subject_type: string;
  filters: PredicateFilter[];
  /** SELECT only. */
  return_fields?: string[];
  /** SUM only. */
  aggregate_path?: string;
}

/** Predicate response (mirrors snake_case `PredicateQueryResponseDTO`). */
export interface PredicateQueryResponse {
  result_mode: QueryResultMode;
  execution_mode: QueryExecutionMode;
  platform_id: string;
  count?: number | null;
  aggregate?: number | null;
  matches?: unknown;
}

/** One traverse source scope (mirrors `TraverseSourceScopeDTO`). */
export interface TraverseSourceScope {
  subject_type: string;
  /** Optional; empty means "all reference paths for this source subject type". */
  reference_paths?: string[];
}

/**
 * Conceptual flattened traverse request (mirrors `TraverseQueryRequestDTO`).
 *
 * NOTE: there is deliberately no nested `target` object. The target subject
 * type and dpp id are top-level fields.
 */
export interface TraverseQueryRequest {
  execution_mode: QueryExecutionMode;
  subject_type: string;
  dpp_id: string;
  /** Optional; pins the traverse to an exact target revision. */
  revision_number?: number;
  sources: TraverseSourceScope[];
}

/** Traverse response (mirrors snake_case `TraverseQueryResponseDTO`). */
export interface TraverseQueryResponse {
  platform_id: string;
  subject_type: string;
  dpp_id: string;
  matches: unknown[];
}

/** Wrapped execution result that also exposes the client-measured duration. */
export interface QueryExecution<T> {
  response: T;
  durationMs: number;
}

// ---------------------------------------------------------------------------
// Query parameter metadata (used to guide the builder; see QueryMetadataService)
// ---------------------------------------------------------------------------

export type QueryValueType = 'TEXT' | 'NUMBER' | 'BOOLEAN' | 'DATE' | 'ENUM' | 'REFERENCE';

export type ReferenceType = 'HARD' | 'SOFT' | 'BOTH';

export interface QueryParameterMetadata {
  subjectType: string;
  path: string;
  label: string;
  valueType: QueryValueType;
  operators: PredicateOperator[];
  /** Original JSON-Schema scalar values; preserving these avoids stringifying numeric/boolean enums. */
  enumValues?: unknown[];
  required?: boolean;
  description?: string;
}

export interface ReferencePathMetadata {
  sourceSubjectType: string;
  referencePath: string;
  targetSubjectType?: string;
  label?: string;
  referenceType?: ReferenceType;
}

export interface SubjectTypeMetadata {
  subjectType: string;
  predicateParameters: QueryParameterMetadata[];
  referencePaths: ReferencePathMetadata[];
  /** True when this metadata was synthesized by the local fallback provider. */
  isFallback?: boolean;
}

// ---------------------------------------------------------------------------
// S4 benchmark result shapes (rendered when a backend can supply them)
// ---------------------------------------------------------------------------

export type S4QueryCategory = 'PREDICATE' | 'TRAVERSE';

/** Mirrors one entry of the workload-generator S4 summary `queries` array. */
export interface S4QuerySummary {
  query_id: string;
  query_category: S4QueryCategory;
  subject_type: string;
  source_subject_type?: string;
  result_mode: string;
  duration_indexed_ms?: number | null;
  duration_on_demand_ms?: number | null;
  speedup_factor?: number | null;
  equivalent: boolean;
  error_message?: string | null;
  count?: number | null;
  aggregate?: number | null;
}

/** Mirrors the workload-generator S4 summary document. */
export interface S4BenchmarkSummary {
  scenario_name: string;
  run_id: string;
  seed: number;
  scale: string;
  total_dpp_count: number;
  generated_revision_count: number;
  success: boolean;
  queries: S4QuerySummary[];
}
