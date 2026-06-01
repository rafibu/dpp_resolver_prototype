import {TestBed} from '@angular/core/testing';
import {signal} from '@angular/core';
import {provideRouter} from '@angular/router';
import {beforeEach, describe, expect, it} from 'vitest';
import {BrowserAnimationsModule} from '@angular/platform-browser/animations';
import {FederationMapComponent} from './federation-map.component';
import {FederationService} from '../../core/federation.service';
import {PlatformStatus} from '../../core/models/federation.model';

describe('FederationMapComponent', () => {
  let federationServiceSpy: any;

  beforeEach(async () => {
    const overview = {
      resolver: { external_url: 'http://resolver', status: PlatformStatus.RUNNING },
      platforms: [
        {
          platform_id: 'p1',
          stack: 'spring-postgres',
          issuer_id: 'i1',
          subject_types: ['t1'],
          external_url: 'http://p1',
          status: PlatformStatus.RUNNING,
          created_at: '2026-01-01T00:00:00Z'
        }
      ]
    };

    federationServiceSpy = {
      federation: signal(overview),
      platforms: signal(overview.platforms),
      resolverUrl: signal('http://resolver')
    };

    await TestBed.configureTestingModule({
      imports: [FederationMapComponent, BrowserAnimationsModule],
      providers: [
        { provide: FederationService, useValue: federationServiceSpy },
        provideRouter([])
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(FederationMapComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should summarize the federation', () => {
    const fixture = TestBed.createComponent(FederationMapComponent);
    expect(fixture.componentInstance.runningCount()).toBe(1);
    expect(fixture.componentInstance.statusSummary()).toBe('1/1 running');
    expect(fixture.componentInstance.subjectTypes()).toEqual(['t1']);
  });
});
