import {CommonModule} from '@angular/common';
import {Component, computed, inject} from '@angular/core';
import {RouterLink, RouterLinkActive, RouterOutlet} from '@angular/router';
import {MatChipsModule} from '@angular/material/chips';
import {MatIconModule} from '@angular/material/icon';
import {MatTabsModule} from '@angular/material/tabs';
import {FederationService} from '../../core/federation.service';

@Component({
  selector: 'app-resolver-detail',
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
  templateUrl: './resolver-detail.component.html',
  styleUrl: './resolver-detail.component.scss'
})
export class ResolverDetailComponent {
  private federationService = inject(FederationService);

  public resolver = computed(() => this.federationService.federation()?.resolver ?? null);
}
