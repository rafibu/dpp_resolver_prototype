import {TestBed} from '@angular/core/testing';
import {provideRouter} from '@angular/router';
import {ScenarioRunnerComponent} from './scenario-runner.component';
import {FactoryService} from '../../core/factory.service';
import {of} from 'rxjs';
import {beforeEach, describe, expect, it, vi} from 'vitest';

describe('ScenarioRunnerComponent', () => {
  let factoryServiceSpy: any;

  beforeEach(async () => {
    factoryServiceSpy = {
      runScenario: vi.fn().mockReturnValue(of({ scenario_id: 's1', status: 'passed', steps: [], report_md: '# Report' })),
      getScenarioStatus: vi.fn().mockReturnValue(of({ status: 'passed', steps: [], report_md: '# Report' }))
    };

    await TestBed.configureTestingModule({
      imports: [ScenarioRunnerComponent],
      providers: [
        { provide: FactoryService, useValue: factoryServiceSpy },
        provideRouter([])
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(ScenarioRunnerComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should run scenario and poll status', () => {
    const fixture = TestBed.createComponent(ScenarioRunnerComponent);
    fixture.componentInstance.runScenario('s1');

    expect(factoryServiceSpy.runScenario).toHaveBeenCalledWith('s1');
    // startPolling uses interval, so we might need fakeAsync for full verification
  });

  it('makes S4 runnable and keeps the Query Builder as a secondary action', () => {
    const fixture = TestBed.createComponent(ScenarioRunnerComponent);
    fixture.detectChanges();
    const s4 = fixture.componentInstance.scenarios.find(scenario => scenario.id === 's4');
    expect(s4?.title).toBe('S4 — Query Evaluation');
    expect(s4?.kind).toBe('run');
    expect(s4?.route).toBe('/query-builder');
    expect(fixture.nativeElement.textContent).toContain('S4 — Query Evaluation');
    fixture.componentInstance.runScenario('s4');
    expect(factoryServiceSpy.runScenario).toHaveBeenCalledWith('s4');
  });

  it('makes S5 runnable and renders its returned report', async () => {
    const fixture = TestBed.createComponent(ScenarioRunnerComponent);
    fixture.detectChanges();
    const s5 = fixture.componentInstance.scenarios.find(scenario => scenario.id === 's5');
    expect(s5?.title).toBe('S5 — Offline Validation');
    expect(s5?.kind).toBe('run');
    fixture.componentInstance.runScenario('s5');
    expect(factoryServiceSpy.runScenario).toHaveBeenCalledWith('s5');
    await Promise.resolve();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Report');
  });
});
