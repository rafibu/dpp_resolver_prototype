import {TestBed} from '@angular/core/testing';
import {signal} from '@angular/core';
import {of, throwError} from 'rxjs';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {S4ScenarioComponent} from './s4-scenario.component';
import {FederationService} from '../../core/federation.service';
import {ResolverService} from '../../core/resolver.service';
import {QueryService} from '../../core/query.service';

describe('S4ScenarioComponent', () => {
  let queryServiceSpy: any;

  beforeEach(() => {
    queryServiceSpy = {
      isS4BenchmarkAvailable: () => false,
      runS4Benchmark: vi.fn().mockReturnValue(throwError(() => new Error('not exposed over HTTP'))),
      executePredicate: vi.fn().mockReturnValue(of({response: {}, durationMs: 1})),
      executeTraverse: vi.fn().mockReturnValue(of({response: {}, durationMs: 1}))
    };

    TestBed.configureTestingModule({
      imports: [S4ScenarioComponent],
      providers: [
        {provide: FederationService, useValue: {platforms: signal([]), resolverUrl: () => undefined}},
        {provide: ResolverService, useValue: {listSchemasForSubjectType: () => of([])}},
        {provide: QueryService, useValue: queryServiceSpy}
      ]
    });
  });

  it('renders the S4: Query Evaluation page referencing predicate and traverse benchmarks', () => {
    const fixture = TestBed.createComponent(S4ScenarioComponent);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('S4: Query Evaluation');
    expect(text).toContain('Predicate query benchmark');
    expect(text).toContain('Traverse query benchmark');
  });

  it('marks the automated benchmark as unavailable over HTTP', () => {
    const fixture = TestBed.createComponent(S4ScenarioComponent);
    expect(fixture.componentInstance.benchmarkAvailable).toBe(false);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('not exposed over HTTP');
  });

  it('surfaces a clear error if the benchmark is triggered', () => {
    const fixture = TestBed.createComponent(S4ScenarioComponent);
    fixture.componentInstance.runBenchmark();
    expect(queryServiceSpy.runS4Benchmark).toHaveBeenCalled();
    expect(fixture.componentInstance.error()).toContain('not exposed over HTTP');
  });

  it('separates predicate and traverse results when a summary is present', () => {
    const fixture = TestBed.createComponent(S4ScenarioComponent);
    fixture.componentInstance.summary.set({
      scenario_name: 's4', run_id: 'r1', seed: 1, scale: 'small',
      total_dpp_count: 10, generated_revision_count: 2, success: true,
      queries: [
        {query_id: 'q1', query_category: 'PREDICATE', subject_type: 'pv_module', result_mode: 'COUNT', equivalent: true},
        {query_id: 't1', query_category: 'TRAVERSE', subject_type: 'component', result_mode: 'TRAVERSE', equivalent: true}
      ]
    });
    expect(fixture.componentInstance.predicateQueries().length).toBe(1);
    expect(fixture.componentInstance.traverseQueries().length).toBe(1);
  });
});
