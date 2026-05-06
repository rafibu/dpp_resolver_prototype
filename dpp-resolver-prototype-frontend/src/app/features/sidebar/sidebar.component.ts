import { Component, inject, signal, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FederationService } from '../../core/federation.service';
import { FactoryService } from '../../core/factory.service';
import { ToastService } from '../../core/toast.service';
import { PlatformInfo, PlatformStatus } from '../../core/models/federation.model';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { SpawnPlatformModalComponent } from '../spawn-platform-modal/spawn-platform-modal.component';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, SpawnPlatformModalComponent],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.scss'
})
export class SidebarComponent {
  public federationService = inject(FederationService);
  private factoryService = inject(FactoryService);
  private toastService = inject(ToastService);

  @ViewChild('spawnModal') spawnModal!: SpawnPlatformModalComponent;

  public platforms = this.federationService.platforms;
  public processing = signal<Record<string, boolean>>({});

  public isDefaultPlatform(id: string): boolean {
    return ['platform-a', 'platform-b', 'platform-c'].includes(id);
  }

  public onPause(id: string): void {
    this.wrapAction(id, this.factoryService.pausePlatform(id), 'Paused');
  }

  public onResume(id: string): void {
    this.wrapAction(id, this.factoryService.resumePlatform(id), 'Resumed');
  }

  public onReset(id: string): void {
    this.wrapAction(id, this.factoryService.resetPlatform(id), 'Reset');
  }

  public onDelete(id: string): void {
    if (confirm(`Are you sure you want to delete platform ${id}?`)) {
      this.wrapAction(id, this.factoryService.deletePlatform(id), 'Deleted');
    }
  }

  private wrapAction(id: string, obs: any, actionName: string): void {
    this.processing.update(p => ({ ...p, [id]: true }));
    obs.subscribe({
      next: () => {
        this.toastService.success(`Platform ${id} ${actionName} successfully`);
        this.federationService.refresh().subscribe();
        this.processing.update(p => ({ ...p, [id]: false }));
      },
      error: (err: any) => {
        this.toastService.error(`Failed to ${actionName.toLowerCase()} platform ${id}: ${err.message || 'Unknown error'}`);
        this.processing.update(p => ({ ...p, [id]: false }));
      }
    });
  }

  public onSpawnNew(): void {
    this.spawnModal.open();
  }
}
