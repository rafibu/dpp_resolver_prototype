import { TestBed } from '@angular/core/testing';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { FactoryService } from './factory.service';
import { PlatformService } from './platform.service';
import { ResolverService } from './resolver.service';
import { environment } from '../../environments/environment';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

describe('API Services', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        FactoryService,
        PlatformService,
        ResolverService,
        provideHttpClient(),
        provideHttpClientTesting()
      ]
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  describe('FactoryService', () => {
    it('should call pause platform', () => {
      const service = TestBed.inject(FactoryService);
      service.pausePlatform('p1').subscribe();
      const req = httpMock.expectOne(`${environment.factoryUrl}/platforms/p1/pause`);
      expect(req.request.method).toBe('POST');
      req.flush({});
    });

    it('should get logs with query param', () => {
      const service = TestBed.inject(FactoryService);
      service.getPlatformLogs('p1', 50).subscribe();
      const req = httpMock.expectOne(`${environment.factoryUrl}/platforms/p1/logs?lines=50`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });
  });

  describe('PlatformService', () => {
    it('should list DPPs', () => {
      const service = TestBed.inject(PlatformService);
      service.listDpps('http://p1').subscribe();
      const req = httpMock.expectOne(`http://p1/dpps`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });
  });

  describe('ResolverService', () => {
    it('should get schema', () => {
      const service = TestBed.inject(ResolverService);
      service.getSchema('http://resolver', 'type1', 1, 0).subscribe();
      const req = httpMock.expectOne(`http://resolver/schemas/type1/1.0`);
      expect(req.request.method).toBe('GET');
      req.flush({});
    });
  });
});
