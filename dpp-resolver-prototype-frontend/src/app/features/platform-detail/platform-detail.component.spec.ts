import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { describe, it, expect, beforeEach } from 'vitest';
import { PlatformDetailComponent } from './platform-detail.component';
import { FederationService } from '../../core/federation.service';
import { PlatformStatus } from '../../core/models/federation.model';

describe('PlatformDetailComponent', () => {
  beforeEach(async () => {
    const platform = {
      platform_id: 'p1',
      stack: 'spring-postgres',
      issuer_id: 'issuer',
      subject_types: ['pv_module'],
      external_url: 'http://p1',
      status: PlatformStatus.RUNNING,
      created_at: '2026-01-01T00:00:00Z'
    };

    await TestBed.configureTestingModule({
      imports: [PlatformDetailComponent],
      providers: [
        { provide: FederationService, useValue: { platforms: signal([platform]) } },
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { paramMap: convertToParamMap({ id: 'p1' }) },
            paramMap: of(convertToParamMap({ id: 'p1' }))
          }
        }
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(PlatformDetailComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should resolve the platform from the federation snapshot', () => {
    const fixture = TestBed.createComponent(PlatformDetailComponent);
    expect(fixture.componentInstance.platform()?.platform_id).toBe('p1');
  });
});
