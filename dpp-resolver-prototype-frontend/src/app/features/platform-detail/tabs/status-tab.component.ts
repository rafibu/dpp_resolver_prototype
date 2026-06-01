import { Component, DestroyRef, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { distinctUntilChanged, finalize, map, take } from 'rxjs';
import { FactoryService } from '../../../core/factory.service';
import { PlatformInfo } from '../../../core/models/federation.model';
import { toErrorMessage } from '../../../core/http-error.utils';

@Component({
  selector: 'app-status-tab',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatProgressBarModule,
    MatTooltipModule
  ],
  templateUrl: './status-tab.component.html',
  styleUrl: './status-tab.component.scss'
})
export class StatusTabComponent {
  private route = inject(ActivatedRoute);
  private factoryService = inject(FactoryService);
  private destroyRef = inject(DestroyRef);

  public platform = signal<PlatformInfo | null>(null);
  public loading = signal(false);
  public error = signal<string | null>(null);

  constructor() {
    this.route.parent?.paramMap.pipe(
      map(params => params.get('id')),
      distinctUntilChanged(),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(id => {
      if (id) {
        this.loadStatus(id);
      }
    });
  }

  public refresh(): void {
    const id = this.platform()?.platform_id;
    if (id) {
      this.loadStatus(id);
    }
  }

  private loadStatus(id: string): void {
    this.loading.set(true);
    this.error.set(null);
    this.factoryService.getPlatform(id).pipe(
      take(1),
      finalize(() => this.loading.set(false))
    ).subscribe({
      next: platform => this.platform.set(platform),
      error: err => this.error.set(toErrorMessage(err, `Failed to load ${id}`))
    });
  }
}
