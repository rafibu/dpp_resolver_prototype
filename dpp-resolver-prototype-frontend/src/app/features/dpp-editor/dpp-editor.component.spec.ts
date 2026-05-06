import { TestBed } from '@angular/core/testing';
import { DppEditorComponent } from './dpp-editor.component';
import { PlatformService } from '../../core/platform.service';
import { FederationService } from '../../core/federation.service';
import { ResolverService } from '../../core/resolver.service';
import { ToastService } from '../../core/toast.service';
import { of, BehaviorSubject } from 'rxjs';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { signal } from '@angular/core';
import { provideMonacoEditor } from 'ngx-monaco-editor-v2';
import { canonicalize, sha256 } from '../../core/utils/crypto.utils';

describe('DppEditorComponent', () => {
  let platformServiceSpy: any;
  let federationServiceSpy: any;
  let resolverServiceSpy: any;
  let toastServiceSpy: any;
  let paramsSubject: BehaviorSubject<any>;

  beforeEach(async () => {
    paramsSubject = new BehaviorSubject({ id: 'p1', dppId: 'p1-dpp1' });

    platformServiceSpy = {
      getDpp: vi.fn().mockReturnValue(of({
        dpp_id: 'p1-dpp1',
        revisions: [{ version: 1, payload: { a: 1 }, hash: 'h1', schema_ref: 'type/1.0', timestamp: '2026-01-01' }]
      })),
      reviseDpp: vi.fn().mockReturnValue(of({}))
    };

    federationServiceSpy = {
      getPlatformById: vi.fn().mockReturnValue(of({ external_url: 'http://p1' })),
      resolverUrl: signal('http://resolver')
    };

    resolverServiceSpy = {
      getSchema: vi.fn().mockReturnValue(of({}))
    };

    toastServiceSpy = {
      success: vi.fn(),
      error: vi.fn()
    };

    await TestBed.configureTestingModule({
      imports: [DppEditorComponent],
      providers: [
        { provide: PlatformService, useValue: platformServiceSpy },
        { provide: FederationService, useValue: federationServiceSpy },
        { provide: ResolverService, useValue: resolverServiceSpy },
        { provide: ToastService, useValue: toastServiceSpy },
        {
          provide: ActivatedRoute,
          useValue: {
            params: paramsSubject.asObservable()
          }
        },
        provideRouter([]),
        provideMonacoEditor()
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(DppEditorComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should load DPP data on init', async () => {
    const fixture = TestBed.createComponent(DppEditorComponent);
    fixture.detectChanges();
    await Promise.resolve();
    expect(federationServiceSpy.getPlatformById).toHaveBeenCalled();
  });

  it('should verify hash correctly', async () => {
    const fixture = TestBed.createComponent(DppEditorComponent);
    fixture.detectChanges();

    // Explicitly set a payload and its correct hash
    const payload = { test: 123 };
    const jcs = canonicalize(payload);
    const expectedHash = await sha256(jcs);

    fixture.componentInstance.currentRevision.set({
      version: 1,
      payload: payload,
      hash: expectedHash,
      schema_ref: 'type/1.0',
      timestamp: '2026-01-01'
    });

    await fixture.componentInstance.verifyHash();
    expect(fixture.componentInstance.hashVerification()).toBe('success');
    expect(toastServiceSpy.success).toHaveBeenCalled();
  });
});
