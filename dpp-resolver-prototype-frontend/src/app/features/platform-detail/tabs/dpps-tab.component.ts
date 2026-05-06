import { Component, inject, signal, OnInit, ViewChild, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { PlatformService } from '../../../core/platform.service';
import { FederationService } from '../../../core/federation.service';
import { DppSummary, DppDetail } from '../../../core/models/api.model';
import { switchMap, map, of } from 'rxjs';
import { CreateDppModalComponent } from '../create-dpp-modal/create-dpp-modal.component';
import { PollingService } from '../../../core/polling.service';

@Component({
  selector: 'app-dpps-tab',
  standalone: true,
  imports: [CommonModule, RouterLink, CreateDppModalComponent],
  templateUrl: './dpps-tab.component.html',
  styleUrl: './dpps-tab.component.scss'
})
export class DppsTabComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private platformService = inject(PlatformService);
  private federationService = inject(FederationService);
  private pollingService = inject(PollingService);

  @ViewChild('createDppModal') createDppModal!: CreateDppModalComponent;

  public platformId = signal<string | null>(null);
  public platformUrl = signal<string | null>(null);
  public issuerId = signal<string>('');
  public subjectTypes = signal<string[]>([]);
  public dpps = signal<DppSummary[]>([]);
  public loading = signal(false);

  public expandedDpp = signal<string | null>(null);
  public dppDetail = signal<DppDetail | null>(null);
  public loadingDetail = signal(false);

  private unregisterPolling?: () => void;

  ngOnInit(): void {
    this.route.parent?.params.subscribe(params => {
      const id = params['id'];
      this.platformId.set(id);
      this.loadDpps(id);
      this.startPolling();
    });
  }

  ngOnDestroy(): void {
    this.unregisterPolling?.();
  }

  private startPolling(): void {
    this.unregisterPolling?.();
    this.unregisterPolling = this.pollingService.register(() => {
      const id = this.platformId();
      if (id) this.loadDpps(id);
    });
  }

  private loadDpps(id: string): void {
    if (!this.dpps().length) this.loading.set(true);

    this.federationService.getPlatformById(id).pipe(
      switchMap(p => {
        if (!p) return of([]);
        this.platformUrl.set(p.external_url);
        this.issuerId.set(p.issuer_id);
        this.subjectTypes.set(p.subject_types);
        return this.platformService.listDpps(p.external_url);
      })
    ).subscribe({
      next: (dpps) => {
        this.dpps.set(dpps);
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  public openCreateModal(): void {
    const pId = this.platformId();
    const url = this.platformUrl();
    if (pId && url) {
      this.createDppModal.open(pId, url, this.issuerId(), this.subjectTypes());
    }
  }

  public toggleExpand(dppId: string): void {
    if (this.expandedDpp() === dppId) {
      this.expandedDpp.set(null);
      this.dppDetail.set(null);
    } else {
      this.expandedDpp.set(dppId);
      this.loadDppDetail(dppId);
    }
  }

  private loadDppDetail(dppId: string): void {
    const url = this.platformUrl();
    if (!url) return;

    this.loadingDetail.set(true);
    this.platformService.getDpp(url, dppId).subscribe({
      next: (detail) => {
        this.dppDetail.set(detail);
        this.loadingDetail.set(false);
      },
      error: () => this.loadingDetail.set(false)
    });
  }
}
