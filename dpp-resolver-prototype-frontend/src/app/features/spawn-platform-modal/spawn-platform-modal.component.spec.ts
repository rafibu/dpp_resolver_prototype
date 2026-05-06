import { TestBed } from '@angular/core/testing';
import { SpawnPlatformModalComponent } from './spawn-platform-modal.component';
import { FactoryService } from '../../core/factory.service';
import { ResolverService } from '../../core/resolver.service';
import { FederationService } from '../../core/federation.service';
import { ToastService } from '../../core/toast.service';
import { of } from 'rxjs';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { signal } from '@angular/core';

describe('SpawnPlatformModalComponent', () => {
  let factoryServiceSpy: any;
  let federationServiceSpy: any;
  let toastServiceSpy: any;

  beforeEach(async () => {
    factoryServiceSpy = {
      spawnPlatform: vi.fn().mockReturnValue(of({ platform_id: 'p-new' }))
    };

    federationServiceSpy = {
      resolverUrl: signal('http://resolver'),
      refresh: vi.fn().mockReturnValue(of({}))
    };

    toastServiceSpy = {
      success: vi.fn(),
      error: vi.fn()
    };

    await TestBed.configureTestingModule({
      imports: [SpawnPlatformModalComponent],
      providers: [
        { provide: FactoryService, useValue: factoryServiceSpy },
        { provide: ResolverService, useValue: {} },
        { provide: FederationService, useValue: federationServiceSpy },
        { provide: ToastService, useValue: toastServiceSpy }
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(SpawnPlatformModalComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should validate form inputs', () => {
    const fixture = TestBed.createComponent(SpawnPlatformModalComponent);
    const comp = fixture.componentInstance;

    comp.issuerId.set('Invalid ID!');
    expect(comp.isValid()).toBe(false);

    comp.issuerId.set('valid-id');
    comp.selectedSubjectTypes.set([]);
    expect(comp.isValid()).toBe(false);

    comp.selectedSubjectTypes.set(['type1']);
    expect(comp.isValid()).toBe(true);
  });

  it('should call factory service on submit', () => {
    const fixture = TestBed.createComponent(SpawnPlatformModalComponent);
    const comp = fixture.componentInstance;

    comp.issuerId.set('test-issuer');
    comp.selectedSubjectTypes.set(['pv_module']);
    comp.onSubmit();

    expect(factoryServiceSpy.spawnPlatform).toHaveBeenCalled();
    expect(toastServiceSpy.success).toHaveBeenCalled();
  });
});
