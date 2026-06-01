import {TestBed} from '@angular/core/testing';
import {signal} from '@angular/core';
import {ActivatedRoute, convertToParamMap, provideRouter} from '@angular/router';
import {BehaviorSubject, of} from 'rxjs';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {provideMonacoEditor} from 'ngx-monaco-editor-v2';
import {DppEditorComponent} from './dpp-editor.component';
import {PlatformService} from '../../core/platform.service';
import {FederationService} from '../../core/federation.service';
import {ResolverService} from '../../core/resolver.service';
import {ToastService} from '../../core/toast.service';
import {PlatformStatus} from '../../core/models/federation.model';
import {canonicalize, sha256} from '../../core/utils/crypto.utils';

describe('DppEditorComponent', () => {
  let platformServiceSpy: any;
  let federationServiceSpy: any;
  let resolverServiceSpy: any;
  let toastServiceSpy: any;
  let paramsSubject: BehaviorSubject<any>;

  beforeEach(async () => {
    paramsSubject = new BehaviorSubject(convertToParamMap({ id: 'p1', dppId: 'p1-dpp1' }));

    platformServiceSpy = {
      getDpp: vi.fn().mockReturnValue(of({
        dpp_id: 'p1-dpp1',
        subject_type: 'type',
        revisions: [{ version: 1, payload: { a: 1 }, hash: 'h1', schema_ref: 'type/1.0' }]
      })),
      reviseDpp: vi.fn().mockReturnValue(of({}))
    };

    federationServiceSpy = {
      platforms: signal([{
        platform_id: 'p1',
        stack: 'spring-postgres',
        issuer_id: 'issuer',
        subject_types: ['type'],
        external_url: 'http://p1',
        status: PlatformStatus.RUNNING,
        created_at: '2026-01-01T00:00:00Z'
      }]),
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
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { paramMap: paramsSubject.asObservable() } },
        provideMonacoEditor()
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(DppEditorComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should load DPP data', () => {
    const fixture = TestBed.createComponent(DppEditorComponent);
    fixture.detectChanges();
    expect(platformServiceSpy.getDpp).toHaveBeenCalledWith('http://p1', 'p1-dpp1');
  });

  it('should verify hash correctly', async () => {
    const fixture = TestBed.createComponent(DppEditorComponent);
    fixture.detectChanges();

    const payload = { test: 123 };
    const expectedHash = await sha256(canonicalize(payload));

    fixture.componentInstance.currentRevision.set({
      version: 1,
      payload,
      hash: expectedHash,
      schema_ref: 'type/1.0'
    });

    await fixture.componentInstance.verifyHash();
    expect(fixture.componentInstance.hashVerification()).toBe('success');
    expect(toastServiceSpy.success).toHaveBeenCalled();
  });
});
