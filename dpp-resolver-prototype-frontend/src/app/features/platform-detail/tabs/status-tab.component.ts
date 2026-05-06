import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { FactoryService } from '../../../core/factory.service';
import { PlatformInfo } from '../../../core/models/federation.model';

@Component({
  selector: 'app-status-tab',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './status-tab.component.html',
  styleUrl: './status-tab.component.scss'
})
export class StatusTabComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private factoryService = inject(FactoryService);

  public platform = signal<PlatformInfo | null>(null);
  public loading = signal(false);

  ngOnInit(): void {
    this.route.parent?.params.subscribe(params => {
      const id = params['id'];
      this.loadStatus(id);
    });
  }

  private loadStatus(id: string): void {
    this.loading.set(true);
    this.factoryService.getPlatform(id).subscribe({
      next: (p) => {
        this.platform.set(p);
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }
}
