import {TestBed} from '@angular/core/testing';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {provideHttpClient} from '@angular/common/http';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';
import {QueryService} from './query.service';
import {
  PredicateOperator,
  PredicateQueryRequest,
  QueryExecutionMode,
  QueryResultMode,
  TraverseQueryRequest
} from './models/query.model';

describe('QueryService', () => {
  let service: QueryService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [QueryService, provideHttpClient(), provideHttpClientTesting()]
    });
    service = TestBed.inject(QueryService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  describe('buildPredicateParams', () => {
    it('encodes Java @ModelAttribute query parameters with indexed filters', () => {
      const request: PredicateQueryRequest = {
        result_mode: QueryResultMode.SELECT,
        execution_mode: QueryExecutionMode.INDEXED,
        subject_types: ['pv_module', 'battery_pack'],
        filters: [
          {path: 'nominal_power_w', operator: PredicateOperator.EQ, value: 0},
          {path: 'lead_mass_kg', operator: PredicateOperator.GT, value: 12.5},
          {path: 'contains_lead', operator: PredicateOperator.EQ, value: true},
          {path: 'production_country', operator: PredicateOperator.IN, value: ['a', 'b']},
          {path: 'disposal_date', operator: PredicateOperator.NOT_EXISTS}
        ],
        return_fields: ['serial_number', 'model']
      };

      const params = QueryService.buildPredicateParams(request);

      expect(params.get('resultMode')).toBe('SELECT');
      expect(params.get('executionMode')).toBe('INDEXED');
      expect(params.getAll('subjectTypes')).toEqual(['pv_module', 'battery_pack']);
      expect(params.get('filters[0].value')).toBe('0');
      expect(params.get('filters[1].value')).toBe('12.5');
      // Booleans are rendered as lowercase strings to match Java parsing.
      expect(params.get('filters[2].value')).toBe('true');
      expect(params.get('filters[3].operator')).toBe('IN');
      expect(params.getAll('filters[3].value')).toEqual(['a', 'b']);
      // EXISTS / NOT_EXISTS omit the value entirely.
      expect(params.has('filters[4].value')).toBe(false);
      expect(params.getAll('returnFields')).toEqual(['serial_number', 'model']);
    });

    it('encodes the SUM aggregate path', () => {
      const params = QueryService.buildPredicateParams({
        result_mode: QueryResultMode.SUM,
        execution_mode: QueryExecutionMode.ON_DEMAND,
        subject_types: ['pv_module'],
        filters: [],
        aggregate_path: 'lead_mass_kg'
      });
      expect(params.get('aggregatePath')).toBe('lead_mass_kg');
    });
  });

  describe('buildTraverseParams', () => {
    it('encodes the flattened request without a nested target object', () => {
      const request: TraverseQueryRequest = {
        execution_mode: QueryExecutionMode.INDEXED,
        subject_type: 'component',
        dpp_id: 'COMP-0001',
        revision_number: 3,
        sources: [
          {subject_type: 'pv_module', reference_paths: ['components.junction_box', 'components.connectors']}
        ]
      };

      const params = QueryService.buildTraverseParams(request);

      expect(params.get('subjectType')).toBe('component');
      expect(params.get('dppId')).toBe('COMP-0001');
      expect(params.get('revisionNumber')).toBe('3');
      expect(params.get('sources[0].subjectType')).toBe('pv_module');
      expect(params.get('sources[0].referencePaths[0]')).toBe('components.junction_box');
      expect(params.get('sources[0].referencePaths[1]')).toBe('components.connectors');
      // The traverse contract is flattened: never a nested target object.
      expect(params.keys().some(key => key.toLowerCase().includes('target'))).toBe(false);
    });
  });

  describe('executePredicate', () => {
    it('GETs the live /query/predicate endpoint and measures duration', () => {
      let durationSeen = -1;
      service.executePredicate('http://platform-a/', {
        result_mode: QueryResultMode.COUNT,
        execution_mode: QueryExecutionMode.INDEXED,
        filters: []
      }).subscribe(execution => {
        durationSeen = execution.durationMs;
      });

      const req = httpMock.expectOne(request =>
        request.method === 'GET' && request.url === 'http://platform-a/query/predicate');
      expect(req.request.params.get('resultMode')).toBe('COUNT');
      expect(req.request.params.has('subjectTypes')).toBe(false);
      req.flush({result_mode: 'COUNT', execution_mode: 'INDEXED', platform_id: 'platform-a', count: 5});
      expect(durationSeen).toBeGreaterThanOrEqual(0);
    });
  });

  describe('executeTraverse', () => {
    it('GETs the live /query/traverse endpoint', () => {
      service.executeTraverse('http://platform-a', {
        execution_mode: QueryExecutionMode.INDEXED,
        subject_type: 'component',
        dpp_id: 'COMP-0001',
        sources: [{subject_type: 'pv_module'}]
      }).subscribe();

      const req = httpMock.expectOne(request =>
        request.method === 'GET' && request.url === 'http://platform-a/query/traverse');
      expect(req.request.params.get('dppId')).toBe('COMP-0001');
      req.flush({platform_id: 'platform-a', subject_type: 'component', dpp_id: 'COMP-0001', matches: []});
    });
  });

  describe('runS4Benchmark', () => {
    it('is not available over HTTP and reports a clear error', () => {
      expect(service.isS4BenchmarkAvailable()).toBe(false);
      let message = '';
      service.runS4Benchmark().subscribe({error: err => (message = err.message)});
      expect(message).toContain('not exposed over HTTP');
    });
  });
});
