import { TestBed } from '@angular/core/testing';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { signal } from '@angular/core';
import { of, throwError, Subject } from 'rxjs';
import { App } from './app';
import { FederationService } from './core/federation.service';
import { ToastService } from './core/toast.service';
import { PollingService } from './core/polling.service';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { provideRouter } from '@angular/router';

describe('App', () => {
  let federationServiceSpy: any;
  let toastServiceSpy: any;
  let pollingServiceSpy: any;

  beforeEach(async () => {
    federationServiceSpy = {
      discover: vi.fn(),
      error: signal<string | null>(null),
      platforms: signal([]),
      resolverUrl: signal('http://resolver')
    };

    toastServiceSpy = {
      toasts: signal([])
    };

    pollingServiceSpy = {
      hasError: signal(false),
      lastSuccess: signal(null)
    };

    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        { provide: FederationService, useValue: federationServiceSpy },
        { provide: ToastService, useValue: toastServiceSpy },
        { provide: PollingService, useValue: pollingServiceSpy },
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([])
      ]
    }).compileComponents();
  });

  it('should create the app', () => {
    federationServiceSpy.discover.mockReturnValue(of({}));
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should be in ready state if discovery succeeds', () => {
    federationServiceSpy.discover.mockReturnValue(of({}));
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixture.componentInstance.state()).toBe('ready');
  });

  it('should be in error state if discovery fails', () => {
    federationServiceSpy.discover.mockReturnValue(throwError(() => new Error('Failed')));
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixture.componentInstance.state()).toBe('error');
  });

  it('should show loading state while discovering', () => {
    const discoverySubject = new Subject<any>();
    federationServiceSpy.discover.mockReturnValue(discoverySubject.asObservable());
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixture.componentInstance.state()).toBe('loading');

    discoverySubject.next({});
    expect(fixture.componentInstance.state()).toBe('ready');
  });
});
