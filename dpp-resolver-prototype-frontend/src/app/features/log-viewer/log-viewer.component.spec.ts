import {TestBed} from '@angular/core/testing';
import {signal} from '@angular/core';
import {ActivatedRoute, convertToParamMap} from '@angular/router';
import {BehaviorSubject, of} from 'rxjs';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {LogViewerComponent} from './log-viewer.component';
import {FactoryService} from '../../core/factory.service';
import {PollingService} from '../../core/polling.service';
import {ToastService} from '../../core/toast.service';

describe('LogViewerComponent', () => {
  let factoryServiceSpy: any;
  let paramsSubject: BehaviorSubject<any>;

  beforeEach(async () => {
    paramsSubject = new BehaviorSubject(convertToParamMap({ id: 'p1' }));

    factoryServiceSpy = {
      getResolverLogs: vi.fn().mockReturnValue(of([])),
      getPlatformLogs: vi.fn().mockReturnValue(of([
        { timestamp: '2026-01-01T10:00:00Z', level: 'INFO', message: 'Started' },
        { timestamp: '2026-01-01T10:00:01Z', level: 'ERROR', message: 'Failed' }
      ]))
    };

    const pollingServiceSpy = {
      register: vi.fn((cb: () => void) => { cb(); return () => {}; }),
      isTabActive: signal(true),
      lastSuccess: signal<Date | null>(null),
      hasError: signal(false)
    };

    await TestBed.configureTestingModule({
      imports: [LogViewerComponent],
      providers: [
        { provide: FactoryService, useValue: factoryServiceSpy },
        { provide: PollingService, useValue: pollingServiceSpy },
        { provide: ToastService, useValue: { success: vi.fn(), error: vi.fn() } },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { data: {} },
            parent: { paramMap: paramsSubject.asObservable() }
          }
        }
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(LogViewerComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should load logs and filter them', () => {
    const fixture = TestBed.createComponent(LogViewerComponent);
    fixture.detectChanges();

    expect(factoryServiceSpy.getPlatformLogs).toHaveBeenCalledWith('p1');
    expect(fixture.componentInstance.logs().length).toBe(2);

    fixture.componentInstance.searchTerm.set('Failed');
    expect(fixture.componentInstance.filteredLogs().length).toBe(1);
    expect(fixture.componentInstance.filteredLogs()[0].message).toBe('Failed');
  });

  it('should pause polling when toggled', () => {
    const fixture = TestBed.createComponent(LogViewerComponent);
    fixture.detectChanges();

    fixture.componentInstance.togglePause();
    expect(fixture.componentInstance.isPaused()).toBe(true);
  });
});
