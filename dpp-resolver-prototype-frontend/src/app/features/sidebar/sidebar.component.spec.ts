import { TestBed } from '@angular/core/testing';
import { SidebarComponent } from './sidebar.component';
import { FederationService } from '../../core/federation.service';
import { FactoryService } from '../../core/factory.service';
import { ToastService } from '../../core/toast.service';
import { signal } from '@angular/core';
import { PlatformStatus } from '../../core/models/federation.model';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { describe, it, expect, beforeEach, vi } from 'vitest';

describe('SidebarComponent', () => {
  let federationServiceSpy: any;
  let factoryServiceSpy: any;
  let toastServiceSpy: any;

  beforeEach(async () => {
    federationServiceSpy = {
      platforms: signal([
        { platform_id: 'p1', status: PlatformStatus.RUNNING },
        { platform_id: 'platform-a', status: PlatformStatus.RUNNING }
      ]),
      refresh: vi.fn().mockReturnValue(of({}))
    };

    factoryServiceSpy = {
      pausePlatform: vi.fn().mockReturnValue(of({})),
      resumePlatform: vi.fn().mockReturnValue(of({})),
      resetPlatform: vi.fn().mockReturnValue(of({})),
      deletePlatform: vi.fn().mockReturnValue(of({}))
    };

    toastServiceSpy = {
      success: vi.fn(),
      error: vi.fn(),
      show: vi.fn()
    };

    await TestBed.configureTestingModule({
      imports: [SidebarComponent],
      providers: [
        { provide: FederationService, useValue: federationServiceSpy },
        { provide: FactoryService, useValue: factoryServiceSpy },
        { provide: ToastService, useValue: toastServiceSpy },
        provideRouter([])
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(SidebarComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should identify default platforms', () => {
    const fixture = TestBed.createComponent(SidebarComponent);
    expect(fixture.componentInstance.isDefaultPlatform('platform-a')).toBe(true);
    expect(fixture.componentInstance.isDefaultPlatform('p1')).toBe(false);
  });

  it('should call pause platform and show toast', () => {
    const fixture = TestBed.createComponent(SidebarComponent);
    fixture.componentInstance.onPause('p1');
    expect(factoryServiceSpy.pausePlatform).toHaveBeenCalledWith('p1');
    expect(toastServiceSpy.success).toHaveBeenCalledWith(expect.stringContaining('successfully'));
  });
});
