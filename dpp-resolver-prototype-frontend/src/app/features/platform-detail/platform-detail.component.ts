import { Component, inject, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { FederationService } from '../../core/federation.service';
import { PlatformInfo } from '../../core/models/federation.model';

@Component({
  selector: 'app-platform-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './platform-detail.component.html',
  styleUrl: './platform-detail.component.scss'
})
export class PlatformDetailComponent {
  private route = inject(ActivatedRoute);
  private federationService = inject(FederationService);

  public platformId = signal<string | null>(null);
  public platform = signal<PlatformInfo | null>(null);

  constructor() {
    this.route.params.subscribe(params => {
      const id = params['id'];
      this.platformId.set(id);
      this.loadPlatform(id);
    });
  }

  private loadPlatform(id: string): void {
    this.federationService.getPlatformById(id).subscribe(p => {
      if (p) this.platform.set(p);
    });
  }
}
