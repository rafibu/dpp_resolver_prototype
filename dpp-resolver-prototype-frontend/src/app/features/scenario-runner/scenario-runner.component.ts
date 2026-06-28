import {Component, DestroyRef, inject, signal} from '@angular/core';
import {CommonModule} from '@angular/common';
import {Clipboard} from '@angular/cdk/clipboard';
import {RouterLink} from '@angular/router';
import {DomSanitizer, SafeHtml} from '@angular/platform-browser';
import {MatButtonModule} from '@angular/material/button';
import {MatCardModule} from '@angular/material/card';
import {MatChipsModule} from '@angular/material/chips';
import {MatIconModule} from '@angular/material/icon';
import {MatListModule} from '@angular/material/list';
import {MatProgressBarModule} from '@angular/material/progress-bar';
import {MatTooltipModule} from '@angular/material/tooltip';
import {interval, startWith, Subscription, switchMap, takeUntil, takeWhile, timer} from 'rxjs';
import {marked} from 'marked';
import {FactoryService} from '../../core/factory.service';
import {ScenarioId, ScenarioStatus} from '../../core/models/api.model';
import {ToastService} from '../../core/toast.service';
import {toErrorMessage} from '../../core/http-error.utils';

/**
 * How a scenario card behaves:
 *  - `run`: triggers a Factory scenario over HTTP and polls its status (S1–S5).
 *  - `navigate`: opens a dedicated scenario page (S4: Query Evaluation).
 *  - `placeholder`: present but not runnable here (S5 has no HTTP integration).
 */
type ScenarioKind = 'run' | 'navigate' | 'placeholder';

interface ScenarioDefinition {
  id: string;
  kind: ScenarioKind;
  icon: string;
  title: string;
  subtitle: string;
  route?: string;
  statusNote?: string;
}

const RUNNABLE_IDS = new Set<ScenarioId>(['s1', 's2', 's3', 's4', 's5']);

@Component({
  selector: 'app-scenario-runner',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatListModule,
    MatProgressBarModule,
    MatTooltipModule
  ],
  templateUrl: './scenario-runner.component.html',
  styleUrl: './scenario-runner.component.scss'
})
export class ScenarioRunnerComponent {
  private factoryService = inject(FactoryService);
  private clipboard = inject(Clipboard);
  private sanitizer = inject(DomSanitizer);
  private toastService = inject(ToastService);
  private destroyRef = inject(DestroyRef);

  public scenarios: ScenarioDefinition[] = [
    {
      id: 's1',
      kind: 'run',
      icon: 'sync_alt',
      title: 'S1: Reference Stability',
      subtitle: 'Hard references stay pinned while soft references follow issuer migration'
    },
    {
      id: 's2',
      kind: 'run',
      icon: 'schema',
      title: 'S2: Schema Evolution',
      subtitle: 'Historical revisions stay bound to their original schema version'
    },
    {
      id: 's3',
      kind: 'run',
      icon: 'account_tree',
      title: 'S3: Cycle Rejection',
      subtitle: 'The resolver rejects schema-level hard-reference cycles before issuance'
    },
    {
      id: 's4',
      kind: 'run',
      icon: 'manage_search',
      title: 'S4: Query Evaluation',
      subtitle: 'Predicate & traverse query evaluation · INDEXED/ON_DEMAND equivalence · timing/result export',
      route: '/query-builder'
    },
    {
      id: 's5',
      kind: 'run',
      icon: 'cloud_off',
      title: 'S5: Offline Validation',
      subtitle: 'Validate cached referenced-platform data during an offline period'
    }
  ];

  public statuses = signal<Record<string, ScenarioStatus | null>>({});
  public reports = signal<Record<string, SafeHtml | null>>({});
  public runningScenario = signal<string | null>(null);
  public errors = signal<Record<string, string | null>>({});
  private pollSubscription?: Subscription;

  constructor() {
    this.destroyRef.onDestroy(() => this.pollSubscription?.unsubscribe());
  }

  public isRunnable(id: string): boolean {
    return RUNNABLE_IDS.has(id as ScenarioId);
  }

  public runScenario(id: string): void {
    if (!this.isRunnable(id)) {
      return;
    }
    const scenarioId = id as ScenarioId;
    this.pollSubscription?.unsubscribe();
    this.runningScenario.set(id);
    this.setError(id, null);
    this.setStatus(id, null);
    this.setReport(id, null);

    this.factoryService.runScenario(scenarioId).subscribe({
      next: status => {
        this.setStatus(id, status);
        if (status.status === 'pending' || status.status === 'running') {
          this.startPolling(scenarioId);
        } else {
          this.runningScenario.set(null);
          this.renderReport(id, status.report_md);
        }
      },
      error: err => {
        this.runningScenario.set(null);
        this.setError(id, toErrorMessage(err, `Failed to start ${id.toUpperCase()}`));
      }
    });
  }

  public downloadReport(id: string): void {
    const status = this.statusFor(id);
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

  public copyStatus(id: string): void {
    const status = this.statusFor(id);
    if (!status) {
      return;
    }
    if (this.clipboard.copy(this.statusText(id))) {
      this.toastService.success(`${id.toUpperCase()} status copied`);
    } else {
      this.toastService.error(`Could not copy ${id.toUpperCase()} status`);
    }
  }

  public getStepIcon(status: string): string {
    switch (status) {
      case 'passed': return 'check_circle';
      case 'failed': return 'error';
      case 'running': return 'progress_activity';
      default: return 'radio_button_unchecked';
    }
  }

  public isRunning(id: string): boolean {
    return this.runningScenario() === id;
  }

  public statusFor(id: string): ScenarioStatus | null {
    return this.statuses()[id] ?? null;
  }

  public reportFor(id: string): SafeHtml | null {
    return this.reports()[id] ?? null;
  }

  public errorFor(id: string): string | null {
    return this.errors()[id] ?? null;
  }

  public statusText(id: string): string {
    const status = this.statusFor(id);
    return status ? JSON.stringify(status, null, 2) : '';
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
        const status = this.statusFor(id);
        if (status?.status === 'pending' || status?.status === 'running') {
          this.runningScenario.set(null);
          this.setError(id, 'Scenario is still pending after 120 seconds. The Factory accepted the request but did not publish a final status.');
        }
      }
    });
  }

  private renderReport(id: string, markdown?: string): void {
    if (!markdown) {
      return;
    }

    Promise.resolve(marked.parse(markdown)).then(html => {
      this.setReport(id, this.sanitizer.bypassSecurityTrustHtml(html));
    }).catch(() => {
      this.toastService.error('Could not render scenario report');
    });
  }

  private setStatus(id: string, status: ScenarioStatus | null): void {
    this.statuses.update(statuses => ({ ...statuses, [id]: status }));
  }

  private setReport(id: string, report: SafeHtml | null): void {
    this.reports.update(reports => ({ ...reports, [id]: report }));
  }

  private setError(id: string, message: string | null): void {
    this.errors.update(errors => ({ ...errors, [id]: message }));
  }
}
