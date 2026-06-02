import {TestBed} from '@angular/core/testing';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {provideHttpClient} from '@angular/common/http';
import {FactoryService} from './factory.service';
import {PlatformService} from './platform.service';
import {ResolverService} from './resolver.service';
import {environment} from '../../environments/environment';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';

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

    it('should get resolver logs with query param', () => {
      const service = TestBed.inject(FactoryService);
      service.getResolverLogs(25).subscribe();
      const req = httpMock.expectOne(`${environment.factoryUrl}/resolver/logs?lines=25`);
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

    it('should issue DPPs through the platform issue endpoint', () => {
      const service = TestBed.inject(PlatformService);
      service.issueDpp('http://p1', {
        schema_version: { subject_type: 'pv_module', major_version: 1, minor_version: 0 },
        dpp_payload: {}
      }).subscribe();
      const req = httpMock.expectOne(`http://p1/dpps/issue`);
      expect(req.request.method).toBe('POST');
      req.flush({});
    });

    it('should revise DPPs through the platform revise endpoint', () => {
      const service = TestBed.inject(PlatformService);
      service.reviseDpp('http://p1', 'dpp-1', {
        schema_version: { subject_type: 'pv_module', major_version: 1, minor_version: 0 },
        dpp_payload: {}
      }).subscribe();
      const req = httpMock.expectOne(`http://p1/dpps/dpp-1/revise`);
      expect(req.request.method).toBe('POST');
      req.flush({});
    });
  });

  describe('ResolverService', () => {
    it('should get schema', () => {
      const service = TestBed.inject(ResolverService);
      service.getSchema('http://resolver', 'type1', 1, 0).subscribe();
      const req = httpMock.expectOne(`http://resolver/schemas/type1/1/0`);
      expect(req.request.method).toBe('GET');
      req.flush({ schemaDocument: {} });
    });

    it('should publish schema', () => {
      const service = TestBed.inject(ResolverService);
      service.publishSchema('http://resolver', {
        subject_type: 'type1',
        major_version: 2,
        minor_version: 0,
        schema_document: {}
      }).subscribe();
      const req = httpMock.expectOne(`http://resolver/schemas`);
      expect(req.request.method).toBe('POST');
      req.flush({ subjectType: 'type1', majorVersion: 2, minorVersion: 0, schemaDocument: {} });
    });
  });
});
