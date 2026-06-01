import {Component, computed, DestroyRef, effect, inject, signal, viewChild} from '@angular/core';
import {CommonModule} from '@angular/common';
import {FormsModule} from '@angular/forms';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {ActivatedRoute} from '@angular/router';
import {CdkVirtualScrollViewport, ScrollingModule} from '@angular/cdk/scrolling';
import {MatButtonModule} from '@angular/material/button';
import {MatFormFieldModule} from '@angular/material/form-field';
import {MatIconModule} from '@angular/material/icon';
import {MatInputModule} from '@angular/material/input';
import {MatProgressBarModule} from '@angular/material/progress-bar';
import {MatSlideToggleModule} from '@angular/material/slide-toggle';
import {MatTooltipModule} from '@angular/material/tooltip';
import {distinctUntilChanged, finalize, map, take} from 'rxjs';
import {FactoryService} from '../../core/factory.service';
import {LogLine} from '../../core/models/api.model';
import {PollingService} from '../../core/polling.service';
import {ToastService} from '../../core/toast.service';
import {toErrorMessage} from '../../core/http-error.utils';

@Component({
  selector: 'app-log-viewer',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ScrollingModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatSlideToggleModule,
    MatTooltipModule
  ],
  templateUrl: './log-viewer.component.html',
  styleUrl: './log-viewer.component.scss'
})
export class LogViewerComponent {
  private factoryService = inject(FactoryService);
  private pollingService = inject(PollingService);
  private toastService = inject(ToastService);
  private route = inject(ActivatedRoute);
  private destroyRef = inject(DestroyRef);
  private logViewport = viewChild<CdkVirtualScrollViewport>('logViewport');
  private unregisterPolling?: () => void;

  public platformId = signal<string | null>(null);
  public logs = signal<LogLine[]>([]);
  public isPaused = signal(false);
  public searchTerm = signal('');
  public autoScroll = signal(true);
  public loading = signal(false);
  public error = signal<string | null>(null);
  public filteredLogs = computed(() => {
    const term = this.searchTerm().trim().toLowerCase();
    if (!term) {
      return this.logs();
    }
    return this.logs().filter(line =>
      line.message.toLowerCase().includes(term) ||
      line.level.toLowerCase().includes(term)
    );
  });

  constructor() {
    this.route.parent?.paramMap.pipe(
      map(params => params.get('id')),
      distinctUntilChanged(),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(id => {
      this.platformId.set(id);
      this.logs.set([]);
      this.startPolling();
      if (id) {
        this.loadLogs(id);
      }
    });

    effect(() => {
      const viewport = this.logViewport();
      const count = this.filteredLogs().length;
      if (viewport && this.autoScroll() && count > 0) {
        setTimeout(() => viewport.scrollToIndex(count - 1, 'smooth'));
      }
    });

    this.destroyRef.onDestroy(() => this.unregisterPolling?.());
  }

  public togglePause(): void {
    this.isPaused.update(value => !value);
  }

  public scrollToBottom(): void {
    const viewport = this.logViewport();
    if (viewport) {
      viewport.scrollToIndex(Math.max(this.filteredLogs().length - 1, 0), 'smooth');
      this.autoScroll.set(true);
    }
  }

  public copyLine(line: LogLine): void {
    const text = `[${line.timestamp || 'no timestamp'}] ${line.level}: ${line.message}`;
    navigator.clipboard.writeText(text).then(
      () => this.toastService.success('Log line copied'),
      () => this.toastService.error('Could not copy log line')
    );
  }

  public getLevelClass(level: string): string {
    const normalized = level.toUpperCase();
    if (normalized.includes('INFO')) return 'info';
    if (normalized.includes('WARN')) return 'warn';
    if (normalized.includes('ERROR')) return 'error';
    if (normalized.includes('DEBUG')) return 'debug';
    return 'default';
  }

  public trackLog(index: number, line: LogLine): string {
    return `${line.timestamp}-${line.level}-${line.message}-${index}`;
  }

  private startPolling(): void {
    this.unregisterPolling?.();
    this.unregisterPolling = this.pollingService.register(() => {
      const id = this.platformId();
      if (id && !this.isPaused()) {
        this.loadLogs(id, true);
      }
    });
  }

  private loadLogs(id: string, silent = false): void {
    if (!silent) {
      this.loading.set(true);
    }
    this.error.set(null);
    this.factoryService.getPlatformLogs(id).pipe(
      take(1),
      finalize(() => this.loading.set(false))
    ).subscribe({
      next: logs => this.logs.set(logs),
      error: err => this.error.set(toErrorMessage(err, `Failed to load logs for ${id}`))
    });
  }
}
