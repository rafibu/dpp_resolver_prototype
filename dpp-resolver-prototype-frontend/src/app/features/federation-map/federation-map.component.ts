import {Component, computed, inject} from '@angular/core';
import {CommonModule} from '@angular/common';
import {RouterLink} from '@angular/router';
import {MatButtonModule} from '@angular/material/button';
import {MatCardModule} from '@angular/material/card';
import {MatChipsModule} from '@angular/material/chips';
import {MatIconModule} from '@angular/material/icon';
import {MatTooltipModule} from '@angular/material/tooltip';
import {FederationService} from '../../core/federation.service';
import {PlatformInfo, PlatformStatus} from '../../core/models/federation.model';

@Component({
  selector: 'app-federation-map',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatTooltipModule
  ],
  templateUrl: './federation-map.component.html',
  styleUrl: './federation-map.component.scss'
})
export class FederationMapComponent {
  private federationService = inject(FederationService);

  public federation = this.federationService.federation;
  public platforms = this.federationService.platforms;
  public resolverUrl = this.federationService.resolverUrl;
  public runningCount = computed(() => this.platforms().filter(p => p.status === PlatformStatus.RUNNING).length);
  public pausedCount = computed(() => this.platforms().filter(p => p.status === PlatformStatus.PAUSED).length);
  public subjectTypes = computed(() => [...new Set(this.platforms().flatMap(p => p.subject_types))].sort());
  public statusSummary = computed(() => {
    const total = this.platforms().length;
    const running = this.runningCount();
    if (!total) {
      return 'No platforms';
    }
    return `${running}/${total} running`;
  });

  public statusClass(status: PlatformStatus | string): string {
    return status.toLowerCase();
  }

  public platformSubtitle(platform: PlatformInfo): string {
    return `${platform.issuer_id} · ${platform.stack}`;
  }
}
