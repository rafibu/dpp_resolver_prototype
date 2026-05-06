import { Component, inject, signal, OnInit, OnDestroy, ViewChild, ElementRef, computed, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FactoryService } from '../../core/factory.service';
import { ActivatedRoute } from '@angular/router';
import { LogLine } from '../../core/models/api.model';
import { FormsModule } from '@angular/forms';
import { PollingService } from '../../core/polling.service';

@Component({
  selector: 'app-log-viewer',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './log-viewer.component.html',
  styleUrl: './log-viewer.component.scss'
})
export class LogViewerComponent implements OnInit, OnDestroy {
  private factoryService = inject(FactoryService);
  private pollingService = inject(PollingService);
  private route = inject(ActivatedRoute);

  @ViewChild('logContainer') logContainer!: ElementRef;

  public platformId = signal<string | null>(null);
  public logs = signal<LogLine[]>([]);
  public isPaused = signal(false);
  public searchTerm = signal('');
  public autoScroll = signal(true);

  public filteredLogs = computed(() => {
    const term = this.searchTerm().toLowerCase();
    if (!term) return this.logs();
    return this.logs().filter(l =>
      l.message.toLowerCase().includes(term) ||
      l.level.toLowerCase().includes(term)
    );
  });

  private unregisterPolling?: () => void;

  constructor() {
    // Re-scroll when logs change if auto-scroll is on
    effect(() => {
      if (this.logs().length > 0 && this.autoScroll()) {
        setTimeout(() => this.scrollToBottom(), 50);
      }
    });
  }

  ngOnInit(): void {
    this.route.parent?.params.subscribe(params => {
      this.platformId.set(params['id']);
      this.startPolling();
    });
  }

  ngOnDestroy(): void {
    this.unregisterPolling?.();
  }

  public startPolling(): void {
    this.unregisterPolling?.();
    const id = this.platformId();
    if (!id) return;

    this.unregisterPolling = this.pollingService.register(() => {
      if (this.isPaused()) return;
      this.factoryService.getPlatformLogs(id).subscribe(newLogs => {
        if (!this.isPaused() && newLogs.length > 0) {
          this.logs.set(newLogs);
        }
      });
    });
  }

  public togglePause(): void {
    this.isPaused.update(v => !v);
  }

  public scrollToBottom(): void {
    if (this.logContainer) {
      const el = this.logContainer.nativeElement;
      el.scrollTop = el.scrollHeight;
    }
  }

  public onScroll(): void {
    const el = this.logContainer.nativeElement;
    const atBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 20;
    this.autoScroll.set(atBottom);
  }

  public copyLine(line: LogLine): void {
    const text = `[${line.timestamp}] ${line.level}: ${line.message}`;
    navigator.clipboard.writeText(text);
  }

  public getLevelClass(level: string): string {
    const l = level.toUpperCase();
    if (l.includes('INFO')) return 'info';
    if (l.includes('WARN')) return 'warn';
    if (l.includes('ERROR')) return 'error';
    if (l.includes('DEBUG')) return 'debug';
    return '';
  }
}
