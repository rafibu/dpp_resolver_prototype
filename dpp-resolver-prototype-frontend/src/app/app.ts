import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterOutlet, RouterLink } from '@angular/router';
import { FederationService } from './core/federation.service';
import { ToastService } from './core/toast.service';
import { PollingService } from './core/polling.service';
import { environment } from '../environments/environment';
import { SidebarComponent } from './features/sidebar/sidebar.component';
import { CommonModule } from '@angular/common';

type BootstrapState = 'loading' | 'ready' | 'error';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, SidebarComponent, CommonModule],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnInit {
  private federationService = inject(FederationService);
  private toastService = inject(ToastService);
  public pollingService = inject(PollingService);

  public state = signal<BootstrapState>('loading');
  public factoryUrl = environment.factoryUrl;
  public errorMessage = this.federationService.error;
  public toasts = this.toastService.toasts;

  ngOnInit(): void {
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

  removeToast(id: number): void {
    this.toastService.remove(id);
  }
}
