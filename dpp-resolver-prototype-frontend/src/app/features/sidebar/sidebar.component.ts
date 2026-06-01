import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Observable, finalize, take } from 'rxjs';
import { FactoryService } from '../../core/factory.service';
import { FederationService } from '../../core/federation.service';
import { toErrorMessage } from '../../core/http-error.utils';
import { ToastService } from '../../core/toast.service';
import { ConfirmDialogComponent } from '../../shared/confirm-dialog.component';
import { SpawnPlatformModalComponent } from '../spawn-platform-modal/spawn-platform-modal.component';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    RouterLinkActive,
    MatButtonModule,
    MatDividerModule,
    MatIconModule,
    MatListModule,
    MatProgressSpinnerModule,
    MatTooltipModule
  ],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.scss'
})
export class SidebarComponent {
  public federationService = inject(FederationService);
  private factoryService = inject(FactoryService);
  private toastService = inject(ToastService);
  private dialog = inject(MatDialog);

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
    this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Delete platform',
        message: `Delete ${id} and tear down its backing container?`,
        confirmText: 'Delete',
        destructive: true
      }
    }).afterClosed().pipe(take(1)).subscribe(confirmed => {
      if (confirmed) {
        this.wrapAction(id, this.factoryService.deletePlatform(id), 'Deleted');
      }
    });
  }

  public onSpawnNew(): void {
    this.dialog.open(SpawnPlatformModalComponent, {
      autoFocus: 'first-tabbable',
      maxWidth: 'calc(100vw - 2rem)',
      width: '34rem'
    }).afterClosed().pipe(take(1)).subscribe(spawned => {
      if (spawned) {
        this.federationService.refresh().pipe(take(1)).subscribe();
      }
    });
  }

  private wrapAction(id: string, obs: Observable<unknown>, actionName: string): void {
    this.processing.update(p => ({ ...p, [id]: true }));
    obs.pipe(finalize(() => {
      this.processing.update(p => ({ ...p, [id]: false }));
    })).subscribe({
      next: () => {
        this.toastService.success(`Platform ${id} ${actionName} successfully`);
        this.federationService.refresh().pipe(take(1)).subscribe();
      },
      error: (err: unknown) => {
        this.toastService.error(toErrorMessage(err, `Failed to ${actionName.toLowerCase()} platform ${id}`));
      }
    });
  }
}
