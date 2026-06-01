import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { finalize, take } from 'rxjs';
import { FactoryService } from '../../core/factory.service';
import { FederationService } from '../../core/federation.service';
import { toErrorMessage } from '../../core/http-error.utils';
import { ToastService } from '../../core/toast.service';

type PlatformStack = 'spring-postgres' | 'fastapi-mongo';

@Component({
  selector: 'app-spawn-platform-modal',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatChipsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule
  ],
  templateUrl: './spawn-platform-modal.component.html',
  styleUrl: './spawn-platform-modal.component.scss'
})
export class SpawnPlatformModalComponent {
  private factoryService = inject(FactoryService);
  private federationService = inject(FederationService);
  private toastService = inject(ToastService);
  private dialogRef = inject(MatDialogRef<SpawnPlatformModalComponent, boolean>);

  public isSpawning = signal(false);
  public stack = signal<PlatformStack>('spring-postgres');
  public issuerId = signal('');
  public availableSubjectTypes = signal<string[]>(['pv_module', 'battery', 'inverter', 'junction_box']);
  public selectedSubjectTypes = signal<string[]>([]);
  public issuerInvalid = computed(() => !!this.issuerId() && !this.isIssuerIdValid());
  public isValid = computed(() => this.isIssuerIdValid() && this.selectedSubjectTypes().length > 0);

  public close(): void {
    if (!this.isSpawning()) {
      this.dialogRef.close(false);
    }
  }

  public toggleSubjectType(type: string, selected: boolean): void {
    this.selectedSubjectTypes.update(types => {
      if (selected && !types.includes(type)) {
        return [...types, type];
      }
      if (!selected) {
        return types.filter(t => t !== type);
      }
      return types;
    });
  }

  public isIssuerIdValid(): boolean {
    return /^[a-z0-9-]+$/.test(this.issuerId());
  }

  public onSubmit(): void {
    if (!this.isValid()) {
      return;
    }

    this.isSpawning.set(true);
    this.factoryService.spawnPlatform({
      stack: this.stack(),
      issuer_id: this.issuerId(),
      subject_types: this.selectedSubjectTypes()
    }).pipe(
      take(1),
      finalize(() => this.isSpawning.set(false))
    ).subscribe({
      next: platform => {
        this.toastService.success(`Platform ${platform.platform_id} spawned successfully`);
        this.federationService.refresh().pipe(take(1)).subscribe();
        this.dialogRef.close(true);
      },
      error: err => {
        this.toastService.error(toErrorMessage(err, 'Failed to spawn platform'));
      }
    });
  }
}
