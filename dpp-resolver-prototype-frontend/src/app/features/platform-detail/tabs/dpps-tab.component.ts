import {Component, DestroyRef, inject, signal} from '@angular/core';
import {CommonModule} from '@angular/common';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {ActivatedRoute, RouterLink} from '@angular/router';
import {MatButtonModule} from '@angular/material/button';
import {MatChipsModule} from '@angular/material/chips';
import {MatDialog} from '@angular/material/dialog';
import {MatExpansionModule} from '@angular/material/expansion';
import {MatIconModule} from '@angular/material/icon';
import {MatListModule} from '@angular/material/list';
import {MatProgressBarModule} from '@angular/material/progress-bar';
import {MatTableModule} from '@angular/material/table';
import {MatTooltipModule} from '@angular/material/tooltip';
import {distinctUntilChanged, finalize, map, take} from 'rxjs';
import {PlatformService} from '../../../core/platform.service';
import {FederationService} from '../../../core/federation.service';
import {DppDetail, DppSummary} from '../../../core/models/api.model';
import {PollingService} from '../../../core/polling.service';
import {toErrorMessage} from '../../../core/http-error.utils';
import {CreateDppDialogData, CreateDppModalComponent} from '../create-dpp-modal/create-dpp-modal.component';

@Component({
  selector: 'app-dpps-tab',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatChipsModule,
    MatExpansionModule,
    MatIconModule,
    MatListModule,
    MatProgressBarModule,
    MatTableModule,
    MatTooltipModule
  ],
  templateUrl: './dpps-tab.component.html',
  styleUrl: './dpps-tab.component.scss'
})
export class DppsTabComponent {
  private route = inject(ActivatedRoute);
  private platformService = inject(PlatformService);
  private federationService = inject(FederationService);
  private pollingService = inject(PollingService);
  private destroyRef = inject(DestroyRef);
  private dialog = inject(MatDialog);
  private unregisterPolling?: () => void;

  public displayedColumns = ['dpp_id', 'subject_type', 'current_version', 'last_updated', 'expand'];
  public platformId = signal<string | null>(null);
  public platformUrl = signal<string | null>(null);
  public issuerId = signal<string>('');
  public subjectTypes = signal<string[]>([]);
  public dpps = signal<DppSummary[]>([]);
  public loading = signal(false);
  public error = signal<string | null>(null);
  public expandedDpp = signal<string | null>(null);
  public dppDetail = signal<DppDetail | null>(null);
  public loadingDetail = signal(false);
  public detailError = signal<string | null>(null);

  constructor() {
    this.route.parent?.paramMap.pipe(
      map(params => params.get('id')),
      distinctUntilChanged(),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(id => {
      this.platformId.set(id);
      this.expandedDpp.set(null);
      this.dppDetail.set(null);
      this.startPolling();
      if (id) {
        this.loadDpps(id);
      }
    });

    this.destroyRef.onDestroy(() => this.unregisterPolling?.());
  }

  public openCreateModal(): void {
    const data = this.dialogData();
    if (!data) {
      return;
    }

    this.dialog.open<CreateDppModalComponent, CreateDppDialogData, boolean>(CreateDppModalComponent, {
      autoFocus: 'first-tabbable',
      data,
      maxWidth: 'calc(100vw - 2rem)',
      width: '64rem'
    }).afterClosed().pipe(take(1)).subscribe(created => {
      const id = this.platformId();
      if (created && id) {
        this.loadDpps(id);
      }
    });
  }

  public toggleExpand(dppId: string): void {
    if (this.expandedDpp() === dppId) {
      this.expandedDpp.set(null);
      this.dppDetail.set(null);
      return;
    }

    this.expandedDpp.set(dppId);
    this.loadDppDetail(dppId);
  }

  private startPolling(): void {
    this.unregisterPolling?.();
    this.unregisterPolling = this.pollingService.register(() => {
      const id = this.platformId();
      if (id) {
        this.loadDpps(id, true);
      }
    });
  }

  private loadDpps(id: string, silent = false): void {
    const platform = this.federationService.platforms().find(p => p.platform_id === id);
    if (!platform) {
      this.error.set(`Platform ${id} is not in the current federation snapshot.`);
      this.dpps.set([]);
      return;
    }

    this.platformUrl.set(platform.external_url);
    this.issuerId.set(platform.issuer_id);
    this.subjectTypes.set(platform.subject_types);
    this.error.set(null);

    if (!silent) {
      this.loading.set(true);
    }

    this.platformService.listDpps(platform.external_url).pipe(
      take(1),
      finalize(() => this.loading.set(false))
    ).subscribe({
      next: dpps => this.dpps.set(dpps),
      error: err => this.error.set(toErrorMessage(err, `Failed to load DPPs from ${id}`))
    });
  }

  private loadDppDetail(dppId: string): void {
    const url = this.platformUrl();
    if (!url) {
      return;
    }

    this.loadingDetail.set(true);
    this.detailError.set(null);
    this.platformService.getDpp(url, dppId).pipe(
      take(1),
      finalize(() => this.loadingDetail.set(false))
    ).subscribe({
      next: detail => this.dppDetail.set(detail),
      error: err => this.detailError.set(toErrorMessage(err, `Failed to load ${dppId}`))
    });
  }

  private dialogData(): CreateDppDialogData | null {
    const platformId = this.platformId();
    const platformUrl = this.platformUrl();
    if (!platformId || !platformUrl) {
      return null;
    }

    return {
      platformId,
      platformUrl,
      issuerId: this.issuerId(),
      subjectTypes: this.subjectTypes()
    };
  }
}
