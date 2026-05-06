import { TestBed } from '@angular/core/testing';
import { PlatformDetailComponent } from './platform-detail.component';
import { FederationService } from '../../core/federation.service';
import { of } from 'rxjs';
import { provideRouter, ActivatedRoute } from '@angular/router';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { PlatformStatus } from '../../core/models/federation.model';

describe('PlatformDetailComponent', () => {
  let federationServiceSpy: any;

  beforeEach(async () => {
    federationServiceSpy = {
      getPlatformById: vi.fn().mockReturnValue(of({
        platform_id: 'p1',
        status: PlatformStatus.RUNNING
      }))
    };

    await TestBed.configureTestingModule({
      imports: [PlatformDetailComponent],
      providers: [
        { provide: FederationService, useValue: federationServiceSpy },
        provideRouter([
          { path: 'platforms/:id', component: PlatformDetailComponent }
        ])
      ]
    }).compileComponents();
  });

  it('should create', () => {
    const fixture = TestBed.createComponent(PlatformDetailComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should load platform on init', () => {
    const fixture = TestBed.createComponent(PlatformDetailComponent);
    fixture.detectChanges();
    expect(federationServiceSpy.getPlatformById).toHaveBeenCalled();
  });
});
