import {TestBed} from '@angular/core/testing';
import {signal} from '@angular/core';
import {of, throwError} from 'rxjs';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {QueryBuilderComponent} from './query-builder.component';
import {FederationService} from '../../core/federation.service';
import {ResolverService} from '../../core/resolver.service';
import {QueryService} from '../../core/query.service';
import {PredicateOperator, QueryExecutionMode, QueryResultMode} from '../../core/models/query.model';

const PLATFORM = {
  platform_id: 'platform-a',
  stack: 'spring-postgres',
  issuer_id: 'issuerA',
  subject_types: ['pv_module', 'component', 'battery_pack'],
  external_url: 'http://pa',
  status: 'RUNNING',
  created_at: ''
};

function createComponent(queryServiceOverrides: Partial<QueryService> = {}) {
  const queryServiceSpy = {
    executePredicate: vi.fn().mockReturnValue(of({response: {result_mode: 'SELECT', execution_mode: 'INDEXED', platform_id: 'platform-a', matches: []}, durationMs: 1})),
    executeTraverse: vi.fn().mockReturnValue(of({response: {platform_id: 'platform-a', subject_type: 'component', dpp_id: 'COMP-1', matches: []}, durationMs: 1})),
    isS4BenchmarkAvailable: () => false,
    ...queryServiceOverrides
  };

  TestBed.configureTestingModule({
    imports: [QueryBuilderComponent],
    providers: [
      {provide: FederationService, useValue: {platforms: signal([PLATFORM]), resolverUrl: () => undefined}},
      {provide: ResolverService, useValue: {listSchemasForSubjectType: () => of([])}},
      {provide: QueryService, useValue: queryServiceSpy}
    ]
  });

  const fixture = TestBed.createComponent(QueryBuilderComponent);
  return {fixture, component: fixture.componentInstance, queryServiceSpy};
}

describe('QueryBuilderComponent', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('should create and default-select the running platform', () => {
    const {component} = createComponent();
    expect(component).toBeTruthy();
    expect(component.platformUrl()).toBe('http://pa');
  });

  it('populates possible query parameters when a subject type is selected', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    const paths = component.predicateParameters().map(parameter => parameter.path);
    expect(paths).toContain('contains_lead');
    expect(paths).toContain('nominal_power_w');
  });

  it('shows numeric operators and a numeric value type for numeric fields', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.addFilter();
    const row = component.filters[0];
    component.onFilterPathChange(row, 'nominal_power_w');
    expect(row.valueType).toBe('NUMBER');
    expect(row.operators).toContain(PredicateOperator.GT);
    expect(component.needsValueInput(row)).toBe(true);
  });

  it('uses a boolean value for boolean fields', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.addFilter();
    const row = component.filters[0];
    component.onFilterPathChange(row, 'contains_lead');
    row.operator = PredicateOperator.EQ;
    row.boolValue = true;
    const request = component.buildPredicateRequest();
    expect(request?.filters[0].value).toBe(true);
  });

  it('generates a Java-compatible predicate request for SELECT with return fields', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.resultMode = QueryResultMode.SELECT;
    component.executionMode = QueryExecutionMode.INDEXED;
    component.addFilter();
    component.onFilterPathChange(component.filters[0], 'contains_lead');
    component.filters[0].operator = PredicateOperator.EQ;
    component.filters[0].boolValue = true;
    component.returnFields = ['serial_number'];

    expect(component.buildPredicateRequest()).toEqual({
      result_mode: 'SELECT',
      execution_mode: 'INDEXED',
      subject_types: ['pv_module'],
      filters: [{path: 'contains_lead', operator: 'EQ', value: true}],
      return_fields: ['serial_number']
    });
  });

  it('omits subject_types when no predicate subject type is selected', () => {
    const {component} = createComponent();
    component.onSubjectTypesChange([]);
    component.resultMode = QueryResultMode.COUNT;
    const request = component.buildPredicateRequest();
    expect(request?.subject_types).toBeUndefined();
    expect(component.isPredicateValid()).toBe(true);
  });

  it('omits the value for EXISTS / NOT_EXISTS filters', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.addFilter();
    const row = component.filters[0];
    component.onFilterPathChange(row, 'disposal_date');
    row.operator = PredicateOperator.NOT_EXISTS;
    expect(component.needsValueInput(row)).toBe(false);
    expect(component.buildPredicateRequest()?.filters[0]).toEqual({path: 'disposal_date', operator: 'NOT_EXISTS'});
  });

  it('generates a list value for an enum IN filter', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('battery_pack');
    component.addFilter();
    const row = component.filters[0];
    component.onFilterPathChange(row, 'chemistry');
    row.operator = PredicateOperator.IN;
    row.inValues = ['LFP', 'NMC'];
    expect(component.buildPredicateRequest()?.filters[0].value).toEqual(['LFP', 'NMC']);
  });

  it('rejects non-numeric values for numeric fields', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.addFilter();
    const row = component.filters[0];
    component.onFilterPathChange(row, 'nominal_power_w');
    row.operator = PredicateOperator.GT;
    row.textValue = 'abc';
    expect(component.filterError(row)).toBe('Enter a numeric value.');
    expect(component.isPredicateValid()).toBe(false);
    row.textValue = '400';
    expect(component.filterError(row)).toBeNull();
  });

  it('accepts finite numeric values including zero and rejects infinity', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.addFilter();
    const row = component.filters[0];
    component.onFilterPathChange(row, 'nominal_power_w');

    row.textValue = '0';
    expect(component.filterError(row)).toBeNull();
    expect(component.buildPredicateRequest()?.filters[0].value).toBe(0);

    row.textValue = '12.5';
    expect(component.filterError(row)).toBeNull();
    expect(component.buildPredicateRequest()?.filters[0].value).toBe(12.5);

    row.textValue = 'Infinity';
    expect(component.filterError(row)).toBe('Enter a numeric value.');
  });

  it('validates every numeric IN value before converting the list', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.addFilter();
    const row = component.filters[0];
    component.onFilterPathChange(row, 'nominal_power_w');
    row.operator = PredicateOperator.IN;

    row.textValue = '0, 12.5';
    expect(component.filterError(row)).toBeNull();
    expect(component.buildPredicateRequest()?.filters[0].value).toEqual([0, 12.5]);

    row.textValue = '0, Infinity';
    expect(component.filterError(row)).toBe('All values must be numeric.');
  });

  it('requires trimmed text and strict ISO dates', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.addFilter();
    const row = component.filters[0];

    component.onFilterPathChange(row, 'serial_number');
    row.textValue = '   ';
    expect(component.filterError(row)).toBe('Enter a value.');
    row.textValue = 'PV-001';
    expect(component.filterError(row)).toBeNull();

    component.onFilterPathChange(row, 'disposal_date');
    row.textValue = '2026-06-23';
    expect(component.filterError(row)).toBeNull();
    row.textValue = '2026-06-23T10:15:30Z';
    expect(component.filterError(row)).toBeNull();
    row.textValue = '23.06.2026';
    expect(component.filterError(row)).toBe('Enter an ISO date or date-time.');
    row.textValue = '2026-02-30';
    expect(component.filterError(row)).toBe('Enter an ISO date or date-time.');
  });

  it('requires known enum selections and preserves enum scalar types', () => {
    const {component} = createComponent();
    component.onSubjectTypesChange(['custom']);
    component.predicateMetadata.set({
      subjectType: 'custom',
      predicateParameters: [{
        subjectType: 'custom', path: 'rank', label: 'Rank', valueType: 'ENUM',
        operators: [PredicateOperator.EQ, PredicateOperator.IN], enumValues: [0, 1]
      }],
      referencePaths: []
    });
    component.addFilter();
    const row = component.filters[0];
    component.onFilterPathChange(row, 'rank');

    expect(component.filterError(row)).toBe('Select a value.');
    row.textValue = 0;
    expect(component.filterError(row)).toBeNull();
    expect(component.buildPredicateRequest()?.filters[0].value).toBe(0);
    row.textValue = '0';
    expect(component.filterError(row)).toBe('Select a value from the available enum options.');

    row.operator = PredicateOperator.IN;
    row.inValues = [];
    expect(component.filterError(row)).toBe('Enter at least one value.');
    row.inValues = [0, 1];
    expect(component.filterError(row)).toBeNull();
    expect(component.buildPredicateRequest()?.filters[0].value).toEqual([0, 1]);
  });

  it('requires a numeric aggregate path for SUM and omits return fields', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.resultMode = QueryResultMode.SUM;
    component.returnFields = ['serial_number'];
    expect(component.isPredicateValid()).toBe(false);
    component.aggregatePath = 'lead_mass_kg';
    expect(component.isPredicateValid()).toBe(true);
    const request = component.buildPredicateRequest();
    expect(request?.aggregate_path).toBe('lead_mass_kg');
    expect(request?.return_fields).toBeUndefined();
  });

  it('omits aggregate path and return fields for COUNT', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.resultMode = QueryResultMode.COUNT;
    component.returnFields = ['serial_number'];
    component.aggregatePath = 'lead_mass_kg';
    const request = component.buildPredicateRequest();
    expect(request?.return_fields).toBeUndefined();
    expect(request?.aggregate_path).toBeUndefined();
  });

  it('generates a flattened traverse request with no nested target object', () => {
    const {component} = createComponent();
    component.setQueryType('traverse');
    component.traverseSubjectType = 'component';
    component.dppId = 'COMP-0001';
    component.revisionNumber = 3;
    component.sources = [{subjectType: 'pv_module', referencePaths: ['components.primary_component']}];

    const request = component.buildTraverseRequest();
    expect(request).toEqual({
      execution_mode: 'INDEXED',
      subject_type: 'component',
      dpp_id: 'COMP-0001',
      revision_number: 3,
      sources: [{subject_type: 'pv_module', reference_paths: ['components.primary_component']}]
    });
    expect(component.previewJson()).not.toContain('target');
  });

  it('validates a positive integer revision number', () => {
    const {component} = createComponent();
    component.setQueryType('traverse');
    component.traverseSubjectType = 'component';
    component.dppId = 'COMP-1';
    component.sources = [{subjectType: 'pv_module', referencePaths: []}];
    component.revisionNumber = -1;
    expect(component.traverseError()).toContain('positive integer');
    component.revisionNumber = 2;
    expect(component.isTraverseValid()).toBe(true);
  });

  it('updates the JSON preview when the form changes', () => {
    const {component} = createComponent();
    component.onSubjectTypeChange('pv_module');
    const before = component.previewJson();
    component.addFilter();
    component.onFilterPathChange(component.filters[0], 'contains_lead');
    expect(component.previewJson()).not.toBe(before);
    expect(component.previewJson()).toContain('contains_lead');
  });

  it('submitting a valid predicate query calls executePredicate', () => {
    const {component, queryServiceSpy} = createComponent();
    component.onSubjectTypeChange('pv_module');
    component.resultMode = QueryResultMode.COUNT;
    component.execute();
    expect(queryServiceSpy.executePredicate).toHaveBeenCalledWith('http://pa', expect.objectContaining({
      result_mode: 'COUNT',
      subject_types: ['pv_module']
    }));
  });

  it('submitting a valid traverse query calls executeTraverse with the flattened request', () => {
    const {component, queryServiceSpy} = createComponent();
    component.setQueryType('traverse');
    component.traverseSubjectType = 'component';
    component.dppId = 'COMP-1';
    component.sources = [{subjectType: 'pv_module', referencePaths: []}];
    component.execute();
    expect(queryServiceSpy.executeTraverse).toHaveBeenCalledWith('http://pa', expect.objectContaining({
      subject_type: 'component',
      dpp_id: 'COMP-1',
      sources: [{subject_type: 'pv_module'}]
    }));
  });

  it('renders results in a table and exposes raw JSON', () => {
    const {component} = createComponent({
      executePredicate: vi.fn().mockReturnValue(of({
        response: {result_mode: 'SELECT', execution_mode: 'INDEXED', platform_id: 'platform-a', matches: [{serial_number: 'S-1', model: 'M-1'}]},
        durationMs: 2
      }))
    });
    component.onSubjectTypeChange('pv_module');
    component.resultMode = QueryResultMode.SELECT;
    component.execute();
    const view = component.result();
    expect(view?.rows.length).toBe(1);
    expect(view?.columns).toEqual(['serial_number', 'model']);
    expect(component.rawResultJson()).toContain('platform_id');
  });

  it('displays API errors', () => {
    const {component} = createComponent({
      executePredicate: vi.fn().mockReturnValue(throwError(() => new Error('boom')))
    });
    component.onSubjectTypeChange('pv_module');
    component.resultMode = QueryResultMode.COUNT;
    component.execute();
    expect(component.error()).toContain('boom');
  });
});
