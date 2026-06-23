import {Component, computed, inject, signal} from '@angular/core';
import {CommonModule} from '@angular/common';
import {MatButtonModule} from '@angular/material/button';
import {MatCardModule} from '@angular/material/card';
import {MatChipsModule} from '@angular/material/chips';
import {MatIconModule} from '@angular/material/icon';
import {MatProgressBarModule} from '@angular/material/progress-bar';
import {MatTableModule} from '@angular/material/table';
import {MatTooltipModule} from '@angular/material/tooltip';
import {finalize, take} from 'rxjs';
import {QueryService} from '../../core/query.service';
import {toErrorMessage} from '../../core/http-error.utils';
import {S4BenchmarkSummary, S4QuerySummary} from '../../core/models/query.model';
import {QueryBuilderComponent} from '../query-builder/query-builder.component';

@Component({
  selector: 'app-s4-scenario',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatProgressBarModule,
    MatTableModule,
    MatTooltipModule,
    QueryBuilderComponent
  ],
  templateUrl: './s4-scenario.component.html',
  styleUrl: './s4-scenario.component.scss'
})
export class S4ScenarioComponent {
  private queryService = inject(QueryService);

  public benchmarkAvailable = this.queryService.isS4BenchmarkAvailable();
  public running = signal(false);
  public error = signal<string | null>(null);
  public summary = signal<S4BenchmarkSummary | null>(null);

  public displayedColumns = [
    'query_id', 'execution', 'duration_indexed_ms', 'duration_on_demand_ms', 'count', 'aggregate', 'equivalent', 'error'
  ];

  public predicateQueries = computed<S4QuerySummary[]>(() =>
    (this.summary()?.queries ?? []).filter(query => query.query_category === 'PREDICATE'));
  public traverseQueries = computed<S4QuerySummary[]>(() =>
    (this.summary()?.queries ?? []).filter(query => query.query_category === 'TRAVERSE'));

  /**
   * Attempt to run the automated S4 benchmark. The backend currently exposes no
   * HTTP endpoint for it (it is a `dpp-workload-generator` CLI scenario), so this
   * surfaces a clear, isolated error rather than silently failing.
   */
  public runBenchmark(): void {
    this.running.set(true);
    this.error.set(null);
    this.queryService.runS4Benchmark().pipe(
      take(1),
      finalize(() => this.running.set(false))
    ).subscribe({
      next: summary => this.summary.set(summary),
      error: err => this.error.set(toErrorMessage(err, 'S4 benchmark could not be started'))
    });
  }
}
