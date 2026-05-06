import { TestBed } from '@angular/core/testing';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { FederationService } from './federation.service';
import { FederationOverview, PlatformStatus } from './models/federation.model';
import { environment } from '../../environments/environment';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

describe('FederationService', () => {
  let service: FederationService;
  let httpMock: HttpTestingController;

  const mockOverview: FederationOverview = {
    resolver: {
      external_url: 'http://localhost:8001',
      status: PlatformStatus.RUNNING
    },
    platforms: [
      {
        platform_id: 'platform-a',
        stack: 'spring-postgres',
        issuer_id: 'issuerA',
        subject_types: ['pv_module'],
        external_url: 'http://localhost:8081',
        status: PlatformStatus.RUNNING,
        created_at: new Date().toISOString()
      }
    ]
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        FederationService,
        provideHttpClient(),
        provideHttpClientTesting()
      ]
    });
    service = TestBed.inject(FederationService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should fetch federation overview on refresh', () => {
    service.refresh().subscribe(overview => {
      expect(overview).toEqual(mockOverview);
      expect(service.federation()).toEqual(mockOverview);
    });

    const req = httpMock.expectOne(`${environment.factoryUrl}/federation`);
    expect(req.request.method).toBe('GET');
    req.flush(mockOverview);
  });

  it('should cache overview after first discovery', () => {
    service.discover().subscribe();
    const req = httpMock.expectOne(`${environment.factoryUrl}/federation`);
    req.flush(mockOverview);

    // Second call should not trigger another HTTP request
    service.discover().subscribe(overview => {
      expect(overview).toEqual(mockOverview);
    });
    httpMock.expectNone(`${environment.factoryUrl}/federation`);
  });

  it('should handle error when Factory is unreachable', () => {
    service.refresh().subscribe({
      error: () => {
        expect(service.error()).toContain('Failed to connect to Factory');
      }
    });

    const req = httpMock.expectOne(`${environment.factoryUrl}/federation`);
    req.error(new ProgressEvent('error'));
  });
});
