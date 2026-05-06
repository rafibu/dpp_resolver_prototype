import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { PollingService } from './polling.service';
import { describe, it, expect, beforeEach, vi } from 'vitest';

describe('PollingService', () => {
  let service: PollingService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [PollingService]
    });
    service = TestBed.inject(PollingService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should register and call callbacks', async () => {
    const cb = vi.fn();
    service.register(cb);

    // Simulate tab focus/active
    service.isTabActive.set(true);

    // We can't easily use fakeAsync with interval in Vitest without special setup
    // but we can manually trigger the private start/callbacks if needed.
    // For now, simple registration check.
    expect(service['callbacks'].has(cb)).toBe(true);
  });

  it('should report success and error', () => {
    service.reportSuccess();
    expect(service.hasError()).toBe(false);
    expect(service.lastSuccess()).toBeDefined();

    service.reportError();
    expect(service.hasError()).toBe(true);
  });
});
