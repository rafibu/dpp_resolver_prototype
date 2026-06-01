import { Component, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { map } from 'rxjs';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { FederationService } from '../../core/federation.service';

@Component({
  selector: 'app-platform-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    MatChipsModule,
    MatIconModule,
    MatTabsModule
  ],
  templateUrl: './platform-detail.component.html',
  styleUrl: './platform-detail.component.scss'
})
export class PlatformDetailComponent {
  private route = inject(ActivatedRoute);
  private federationService = inject(FederationService);
  private routePlatformId = toSignal(
    this.route.paramMap.pipe(map(params => params.get('id'))),
    { initialValue: this.route.snapshot.paramMap.get('id') }
  );

  public platformId = computed(() => this.routePlatformId());
  public platform = computed(() => {
    const id = this.platformId();
    if (!id) {
      return null;
    }
    return this.federationService.platforms().find(platform => platform.platform_id === id) ?? null;
  });
}
