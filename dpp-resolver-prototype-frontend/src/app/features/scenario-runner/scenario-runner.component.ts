import { Component, DestroyRef, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { interval, startWith, Subscription, switchMap, takeUntil, takeWhile, timer } from 'rxjs';
import { marked } from 'marked';
import { FactoryService } from '../../core/factory.service';
import { ScenarioStatus } from '../../core/models/api.model';
import { ToastService } from '../../core/toast.service';
import { toErrorMessage } from '../../core/http-error.utils';

type ScenarioId = 's1' | 's2';

@Component({
  selector: 'app-scenario-runner',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatListModule,
    MatProgressBarModule
  ],
  templateUrl: './scenario-runner.component.html',
  styleUrl: './scenario-runner.component.scss'
})
export class ScenarioRunnerComponent {
  private factoryService = inject(FactoryService);
  private sanitizer = inject(DomSanitizer);
  private toastService = inject(ToastService);
  private destroyRef = inject(DestroyRef);

  public s1Status = signal<ScenarioStatus | null>(null);
  public s2Status = signal<ScenarioStatus | null>(null);
  public s1Report = signal<SafeHtml | null>(null);
  public s2Report = signal<SafeHtml | null>(null);
  public runningScenario = signal<ScenarioId | null>(null);
  public errors = signal<Record<ScenarioId, string | null>>({ s1: null, s2: null });
  private pollSubscription?: Subscription;

  constructor() {
    this.destroyRef.onDestroy(() => this.pollSubscription?.unsubscribe());
  }

  public runScenario(id: ScenarioId): void {
    this.pollSubscription?.unsubscribe();
    this.runningScenario.set(id);
    this.setError(id, null);
    this.setStatus(id, null);
    this.setReport(id, null);

    this.factoryService.runScenario(id).subscribe({
      next: status => {
        this.setStatus(id, status);
        this.startPolling(id);
      },
      error: err => {
        this.runningScenario.set(null);
        this.setError(id, toErrorMessage(err, `Failed to start ${id.toUpperCase()}`));
      }
    });
  }

  public downloadReport(id: ScenarioId): void {
    const status = id === 's1' ? this.s1Status() : this.s2Status();
    if (!status?.report_md) {
      return;
    }

    const blob = new Blob([status.report_md], { type: 'text/markdown' });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `report-${id}-${new Date().toISOString()}.md`;
    anchor.click();
    window.URL.revokeObjectURL(url);
  }

  public getStepIcon(status: string): string {
    switch (status) {
      case 'passed': return 'check_circle';
      case 'failed': return 'error';
      case 'running': return 'progress_activity';
      default: return 'radio_button_unchecked';
    }
  }

  public isRunning(id: ScenarioId): boolean {
    return this.runningScenario() === id;
  }

  private startPolling(id: ScenarioId): void {
    this.pollSubscription = interval(2000).pipe(
      startWith(0),
      switchMap(() => this.factoryService.getScenarioStatus(id)),
      takeWhile(status => status.status === 'running' || status.status === 'pending', true),
      takeUntil(timer(120000))
    ).subscribe({
      next: status => {
        this.setStatus(id, status);
        if (status.status === 'passed' || status.status === 'failed') {
          this.runningScenario.set(null);
          this.renderReport(id, status.report_md);
        }
      },
      error: err => {
        this.runningScenario.set(null);
        this.setError(id, toErrorMessage(err, `Failed while polling ${id.toUpperCase()}`));
      },
      complete: () => {
        const status = id === 's1' ? this.s1Status() : this.s2Status();
        if (status?.status === 'pending' || status?.status === 'running') {
          this.runningScenario.set(null);
          this.setError(id, 'Scenario is still pending after 120 seconds. The Factory accepted the request but did not publish a final status.');
        }
      }
    });
  }

  private renderReport(id: ScenarioId, markdown?: string): void {
    if (!markdown) {
      return;
    }

    Promise.resolve(marked.parse(markdown)).then(html => {
      this.setReport(id, this.sanitizer.bypassSecurityTrustHtml(html));
    }).catch(() => {
      this.toastService.error('Could not render scenario report');
    });
  }

  private setStatus(id: ScenarioId, status: ScenarioStatus | null): void {
    if (id === 's1') {
      this.s1Status.set(status);
    } else {
      this.s2Status.set(status);
    }
  }

  private setReport(id: ScenarioId, report: SafeHtml | null): void {
    if (id === 's1') {
      this.s1Report.set(report);
    } else {
      this.s2Report.set(report);
    }
  }

  private setError(id: ScenarioId, message: string | null): void {
    this.errors.update(errors => ({ ...errors, [id]: message }));
  }
}
