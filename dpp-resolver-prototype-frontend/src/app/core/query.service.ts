import {inject, Injectable} from '@angular/core';
import {HttpClient, HttpParams} from '@angular/common/http';
import {map, Observable, throwError} from 'rxjs';
import {
  PredicateFilter,
  PredicateQueryRequest,
  PredicateQueryResponse,
  QueryExecution,
  S4BenchmarkSummary,
  TraverseQueryRequest,
  TraverseQueryResponse,
  VALUE_LESS_OPERATORS
} from './models/query.model';

/**
 * Executes platform-local predicate and reverse-traverse queries.
 *
 * Both endpoints are GET endpoints that the Java platform binds with Spring's
 * `@ModelAttribute`, so the request is encoded as query parameters rather than a
 * JSON body. Top-level field names are camelCase, AND-connected predicate
 * filters are `filters[<index>].<field>`, repeated `filters[i].value` encodes an
 * IN list, repeated `returnFields` encodes the SELECT projection, and traverse
 * optional predicate subject-type scopes are repeated `subjectTypes`, traverse
 * source scopes are `sources[<index>].subjectType` /
 * `sources[<index>].referencePaths[<j>]`. This mirrors the reference encoder in
 * `dpp-workload-generator/src/workload/clients.py` so the frontend, the Java
 * platform, and the Python platform all share one request shape.
 */
@Injectable({
  providedIn: 'root'
})
export class QueryService {
  private http = inject(HttpClient);

  /** Execute a predicate query against a single platform. Duration is measured client-side. */
  executePredicate(platformUrl: string, request: PredicateQueryRequest): Observable<QueryExecution<PredicateQueryResponse>> {
    const params = QueryService.buildPredicateParams(request);
    const started = performance.now();
    return this.http.get<PredicateQueryResponse>(`${stripTrailingSlash(platformUrl)}/query/predicate`, {params}).pipe(
      map(response => ({response, durationMs: performance.now() - started}))
    );
  }

  /** Execute a flattened traverse query against a single platform. Duration is measured client-side. */
  executeTraverse(platformUrl: string, request: TraverseQueryRequest): Observable<QueryExecution<TraverseQueryResponse>> {
    const params = QueryService.buildTraverseParams(request);
    const started = performance.now();
    return this.http.get<TraverseQueryResponse>(`${stripTrailingSlash(platformUrl)}/query/traverse`, {params}).pipe(
      map(response => ({response, durationMs: performance.now() - started}))
    );
  }

  /**
   * Run the automated S4 query-evaluation benchmark (predicate + traverse suite
   * across the federation, INDEXED vs ON_DEMAND equivalence, timing/result
   * export).
   *
   * BACKEND SUPPORT REQUIRED: S4 currently exists only as a `dpp-workload-generator`
   * CLI scenario (`workload/scenarios/s4.py`); neither the Factory nor any
   * platform exposes it over HTTP. This method is intentionally isolated so the
   * UI can present a clear "not available" state today and be wired to a real
   * endpoint later without touching the components. The interactive query
   * builder, by contrast, uses the live per-platform `/query/*` endpoints and
   * works now.
   */
  runS4Benchmark(): Observable<S4BenchmarkSummary> {
    return throwError(() => new Error(
      'The automated S4 query-evaluation benchmark is not exposed over HTTP. ' +
      'It runs only via the dpp-workload-generator CLI (`workload s4`). ' +
      'Use the interactive Query Builder below to evaluate predicate and traverse queries against a live platform.'
    ));
  }

  /** Whether the automated S4 benchmark can be triggered from the UI. */
  isS4BenchmarkAvailable(): boolean {
    return false;
  }

  /** Encode a predicate request into Java's `@ModelAttribute` query-parameter contract. */
  static buildPredicateParams(request: PredicateQueryRequest): HttpParams {
    let params = new HttpParams()
      .set('resultMode', request.result_mode)
      .set('executionMode', request.execution_mode);

    for (const subjectType of request.subject_types ?? []) {
      params = params.append('subjectTypes', subjectType);
    }

    request.filters.forEach((filter, index) => {
      params = params
        .append(`filters[${index}].path`, filter.path)
        .append(`filters[${index}].operator`, filter.operator);
      if (!VALUE_LESS_OPERATORS.has(filter.operator)) {
        for (const value of filterValues(filter)) {
          params = params.append(`filters[${index}].value`, scalar(value));
        }
      }
    });

    for (const field of request.return_fields ?? []) {
      params = params.append('returnFields', field);
    }
    if (request.aggregate_path != null && request.aggregate_path !== '') {
      params = params.set('aggregatePath', request.aggregate_path);
    }
    return params;
  }

  /** Encode the flattened traverse request. Never emits a nested target object. */
  static buildTraverseParams(request: TraverseQueryRequest): HttpParams {
    let params = new HttpParams()
      .set('executionMode', request.execution_mode)
      .set('subjectType', request.subject_type)
      .set('dppId', request.dpp_id);

    if (request.revision_number != null) {
      params = params.set('revisionNumber', String(request.revision_number));
    }

    request.sources.forEach((source, index) => {
      params = params.append(`sources[${index}].subjectType`, source.subject_type);
      (source.reference_paths ?? []).forEach((path, pathIndex) => {
        params = params.append(`sources[${index}].referencePaths[${pathIndex}]`, path);
      });
    });
    return params;
  }
}

function filterValues(filter: PredicateFilter): unknown[] {
  if (filter.value == null) {
    return [];
  }
  return Array.isArray(filter.value) ? filter.value : [filter.value];
}

function scalar(value: unknown): string {
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  return String(value);
}

function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, '');
}
