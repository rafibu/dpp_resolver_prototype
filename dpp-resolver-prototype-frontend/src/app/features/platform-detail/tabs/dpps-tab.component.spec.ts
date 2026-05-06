import { TestBed } from '@angular/core/testing';
import { DppsTabComponent } from './dpps-tab.component';
import { PlatformService } from '../../../core/platform.service';
import { FederationService } from '../../../core/federation.service';
import { of } from 'rxjs';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { signal } from '@angular/core';
import { provideMonacoEditor } from 'ngx-monaco-editor-v2';

describe('DppsTabComponent', () => {
  let platformServiceSpy: any;
  let federationServiceSpy: any;

  beforeEach(async () => {
    platformServiceSpy = {
      listDpps: vi.fn().mockReturnValue(of([])),
      getDpp: vi.fn().mockReturnValue(of({ revisions: [] }))
    };

    federationServiceSpy = {
      getPlatformById: vi.fn().mockReturnValue(of({ external_url: 'http://p1' }))
    };

    await TestBed.configureTestingModule({
      imports: [DppsTabComponent],
      providers: [
        { provide: PlatformService, useValue: platformServiceSpy },
        { provide: FederationService, useValue: federationServiceSpy },
        {
          provide: ActivatedRoute,
          useValue: {
            parent: { params: of({ id: 'p1' }) }
          }
        },
        provideMonacoEditor()
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(DppsTabComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should load DPPs on init', () => {
    const fixture = TestBed.createComponent(DppsTabComponent);
    fixture.detectChanges();
    expect(federationServiceSpy.getPlatformById).toHaveBeenCalledWith('p1');
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
