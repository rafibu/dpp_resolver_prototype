import {TestBed} from '@angular/core/testing';
import {signal} from '@angular/core';
import {ActivatedRoute, convertToParamMap} from '@angular/router';
import {MatDialog} from '@angular/material/dialog';
import {of} from 'rxjs';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {DppsTabComponent} from './dpps-tab.component';
import {PlatformService} from '../../../core/platform.service';
import {FederationService} from '../../../core/federation.service';
import {PollingService} from '../../../core/polling.service';
import {PlatformStatus} from '../../../core/models/federation.model';

describe('DppsTabComponent', () => {
  let platformServiceSpy: any;
  let federationServiceSpy: any;

  beforeEach(async () => {
    platformServiceSpy = {
      listDpps: vi.fn().mockReturnValue(of([])),
      getDpp: vi.fn().mockReturnValue(of({ revisions: [] }))
    };

    federationServiceSpy = {
      platforms: signal([{
        platform_id: 'p1',
        stack: 'spring-postgres',
        issuer_id: 'issuer',
        subject_types: ['pv_module'],
        external_url: 'http://p1',
        status: PlatformStatus.RUNNING,
        created_at: '2026-01-01T00:00:00Z'
      }])
    };

    await TestBed.configureTestingModule({
      imports: [DppsTabComponent],
      providers: [
        { provide: PlatformService, useValue: platformServiceSpy },
        { provide: FederationService, useValue: federationServiceSpy },
        { provide: PollingService, useValue: { register: vi.fn(() => () => {}) } },
        { provide: MatDialog, useValue: { open: vi.fn() } },
        {
          provide: ActivatedRoute,
          useValue: {
            parent: { paramMap: of(convertToParamMap({ id: 'p1' })) }
          }
        }
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(DppsTabComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should load DPPs from the current platform', () => {
    const fixture = TestBed.createComponent(DppsTabComponent);
    fixture.detectChanges();
    expect(platformServiceSpy.listDpps).toHaveBeenCalledWith('http://p1');
  });

  it('should toggle expansion and load detail', () => {
    const fixture = TestBed.createComponent(DppsTabComponent);
    fixture.detectChanges();
    fixture.componentInstance.platformUrl.set('http://p1');
    fixture.componentInstance.toggleExpand('dpp1');
    expect(fixture.componentInstance.expandedDpp()).toBe('dpp1');
    expect(platformServiceSpy.getDpp).toHaveBeenCalledWith('http://p1', 'dpp1');
  });
});
