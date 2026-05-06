import { TestBed } from '@angular/core/testing';
import { FederationMapComponent } from './federation-map.component';
import { FederationService } from '../../core/federation.service';
import { signal } from '@angular/core';
import { PlatformStatus } from '../../core/models/federation.model';
import { provideRouter } from '@angular/router';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';

describe('FederationMapComponent', () => {
  let federationServiceSpy: any;

  beforeEach(async () => {
    federationServiceSpy = {
      federation: signal({
        resolver: { external_url: 'http://resolver', status: PlatformStatus.RUNNING },
        platforms: [
          {
            platform_id: 'p1',
            issuer_id: 'i1',
            subject_types: ['t1'],
            external_url: 'http://p1',
            status: PlatformStatus.RUNNING
          }
        ]
      })
    };

    await TestBed.configureTestingModule({
      imports: [FederationMapComponent, BrowserAnimationsModule],
      providers: [
        { provide: FederationService, useValue: federationServiceSpy },
        provideRouter([])
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(FederationMapComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should compute nodes correctly', () => {
    const fixture = TestBed.createComponent(FederationMapComponent);
    const nodes = fixture.componentInstance.nodes();
    expect(nodes.length).toBe(2); // Resolver + 1 platform
    expect(nodes.find(n => n.id === 'resolver')).toBeDefined();
    expect(nodes.find(n => n.id === 'p1')).toBeDefined();
  });

  it('should compute links correctly', () => {
    const fixture = TestBed.createComponent(FederationMapComponent);
    const links = fixture.componentInstance.links();
    expect(links.length).toBe(1);
    expect(links[0].source).toBe('p1');
    expect(links[0].target).toBe('resolver');
  });
});
