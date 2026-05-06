import { Component, inject, signal, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FactoryService } from '../../core/factory.service';
import { ScenarioStatus, ScenarioStep } from '../../core/models/api.model';
import { interval, Subscription, startWith, switchMap, takeWhile } from 'rxjs';
import { marked } from 'marked';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Component({
  selector: 'app-scenario-runner',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './scenario-runner.component.html',
  styleUrl: './scenario-runner.component.scss'
})
export class ScenarioRunnerComponent implements OnInit, OnDestroy {
  private factoryService = inject(FactoryService);
  private sanitizer = inject(DomSanitizer);

  public s1Status = signal<ScenarioStatus | null>(null);
  public s2Status = signal<ScenarioStatus | null>(null);

  public s1Report = signal<SafeHtml | null>(null);
  public s2Report = signal<SafeHtml | null>(null);

  public isRunning = signal(false);

  private pollSubscription?: Subscription;

  ngOnInit(): void {
    // Load last reports if any (from Factory if supported, or just memory)
  }

  ngOnDestroy(): void {
    this.pollSubscription?.unsubscribe();
  }

  public runScenario(id: 's1' | 's2'): void {
    this.isRunning.set(true);
    if (id === 's1') {
      this.s1Status.set(null);
      this.s1Report.set(null);
    } else {
      this.s2Status.set(null);
      this.s2Report.set(null);
    }

    this.factoryService.runScenario(id).subscribe({
      next: () => this.startPolling(id),
      error: () => this.isRunning.set(false)
    });
  }

  private startPolling(id: 's1' | 's2'): void {
    this.pollSubscription = interval(2000).pipe(
      startWith(0),
      switchMap(() => this.factoryService.getScenarioStatus(id)),
      takeWhile(status => status.status === 'running' || status.status === 'pending', true)
    ).subscribe(status => {
      if (id === 's1') this.s1Status.set(status);
      else this.s2Status.set(status);

      if (status.status === 'passed' || status.status === 'failed') {
        this.isRunning.set(false);
        if (status.report_md) {
          const html = marked.parse(status.report_md) as string;
          const safeHtml = this.sanitizer.bypassSecurityTrustHtml(html);
          if (id === 's1') this.s1Report.set(safeHtml);
          else this.s2Report.set(safeHtml);
        }
      }
    });
  }

  public downloadReport(id: 's1' | 's2'): void {
    const status = id === 's1' ? this.s1Status() : this.s2Status();
    if (!status?.report_md) return;

    const blob = new Blob([status.report_md], { type: 'text/markdown' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report-${id}-${new Date().toISOString()}.md`;
    a.click();
    window.URL.revokeObjectURL(url);
  }

  public getStepIcon(status: string): string {
    switch (status) {
      case 'passed': return '✅';
      case 'failed': return '❌';
      case 'running': return '⏳';
      default: return '⚪';
    }
  }
}
