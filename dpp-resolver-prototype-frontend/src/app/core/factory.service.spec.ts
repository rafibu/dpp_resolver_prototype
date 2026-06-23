import {TestBed} from '@angular/core/testing';
import {provideHttpClient} from '@angular/common/http';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';
import {FactoryService} from './factory.service';
import {environment} from '../../environments/environment';

describe('FactoryService', () => {
  let service: FactoryService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [FactoryService, provideHttpClient(), provideHttpClientTesting()]
    });
    service = TestBed.inject(FactoryService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('posts S5 through the generic scenario endpoint', () => {
    service.runScenario('s5').subscribe();

    const request = httpMock.expectOne(`${environment.factoryUrl}/scenarios/s5`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({});
    request.flush({scenario_id: 's5', status: 'passed', steps: [], report_md: '# S5'});
  });
});
