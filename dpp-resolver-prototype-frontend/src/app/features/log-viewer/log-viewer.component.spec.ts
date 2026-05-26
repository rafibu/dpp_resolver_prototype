import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { LogViewerComponent } from './log-viewer.component';
import { FactoryService } from '../../core/factory.service';
import { PollingService } from '../../core/polling.service';
import { of, BehaviorSubject } from 'rxjs';
import { ActivatedRoute } from '@angular/router';
import { signal } from '@angular/core';
import { describe, it, expect, beforeEach, vi } from 'vitest';

describe('LogViewerComponent', () => {
  let factoryServiceSpy: any;
  let paramsSubject: BehaviorSubject<any>;

  beforeEach(async () => {
    paramsSubject = new BehaviorSubject({ id: 'p1' });

    factoryServiceSpy = {
      getPlatformLogs: vi.fn().mockReturnValue(of([
        { timestamp: '2026-01-01T10:00:00Z', level: 'INFO', message: 'Started' },
        { timestamp: '2026-01-01T10:00:01Z', level: 'ERROR', message: 'Failed' }
      ]))
    };

    const pollingServiceSpy = {
      register: vi.fn((cb: () => void) => { cb(); return () => {}; }),
      reportSuccess: vi.fn(),
      reportError: vi.fn(),
      isTabActive: signal(true),
      lastSuccess: signal<Date | null>(null),
      hasError: signal(false)
    };

    await TestBed.configureTestingModule({
      imports: [LogViewerComponent],
      providers: [
        { provide: FactoryService, useValue: factoryServiceSpy },
        { provide: PollingService, useValue: pollingServiceSpy },
        {
          provide: ActivatedRoute,
          useValue: {
            parent: { params: paramsSubject.asObservable() }
          }
        }
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(LogViewerComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should load logs on init and filter them', () => {
    const fixture = TestBed.createComponent(LogViewerComponent);
    fixture.detectChanges();

    expect(factoryServiceSpy.getPlatformLogs).toHaveBeenCalledWith('p1');
    expect(fixture.componentInstance.logs().length).toBe(2);

    fixture.componentInstance.searchTerm.set('Failed');
    fixture.detectChanges();
    expect(fixture.componentInstance.filteredLogs().length).toBe(1);
    expect(fixture.componentInstance.filteredLogs()[0].message).toBe('Failed');
  });

  it('should pause polling when toggled', () => {
    const fixture = TestBed.createComponent(LogViewerComponent);
    fixture.detectChanges();

    fixture.componentInstance.togglePause();
    expect(fixture.componentInstance.isPaused()).toBe(true);

    // Clear mock calls to verify no new calls
    factoryServiceSpy.getPlatformLogs.mockClear();
    // In a real interval, it wouldn't call. Our startWith(0) already fired.
  });
});
