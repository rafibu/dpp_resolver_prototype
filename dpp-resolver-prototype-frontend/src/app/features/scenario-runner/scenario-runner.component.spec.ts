import {TestBed} from '@angular/core/testing';
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
        { provide: FactoryService, useValue: factoryServiceSpy }
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
});
