import {Component, inject, signal} from '@angular/core';
import {RouterLink, RouterOutlet} from '@angular/router';
import {FederationService} from './core/federation.service';
import {PollingService} from './core/polling.service';
import {environment} from '../environments/environment';
import {SidebarComponent} from './features/sidebar/sidebar.component';
import {CommonModule} from '@angular/common';
import {MatButtonModule} from '@angular/material/button';
import {MatCardModule} from '@angular/material/card';
import {MatIconModule} from '@angular/material/icon';
import {MatProgressSpinnerModule} from '@angular/material/progress-spinner';
import {MatSidenavModule} from '@angular/material/sidenav';
import {MatToolbarModule} from '@angular/material/toolbar';
import {MatTooltipModule} from '@angular/material/tooltip';

type BootstrapState = 'loading' | 'ready' | 'error';

@Component({
  selector: 'app-root',
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    SidebarComponent,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSidenavModule,
    MatToolbarModule,
    MatTooltipModule
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  private federationService = inject(FederationService);
  public pollingService = inject(PollingService);

  public state = signal<BootstrapState>('loading');
  public factoryUrl = environment.factoryUrl;
  public errorMessage = this.federationService.error;

  constructor() {
    this.bootstrap();
  }

  bootstrap(): void {
    this.state.set('loading');
    this.federationService.discover().subscribe({
      next: () => this.state.set('ready'),
      error: () => this.state.set('error')
    });
  }

  retry(): void {
    this.bootstrap();
  }
}
