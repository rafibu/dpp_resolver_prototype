import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { FactoryService } from '../../core/factory.service';
import { ResolverService } from '../../core/resolver.service';
import { FederationService } from '../../core/federation.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-spawn-platform-modal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './spawn-platform-modal.component.html',
  styleUrl: './spawn-platform-modal.component.scss'
})
export class SpawnPlatformModalComponent implements OnInit {
  private factoryService = inject(FactoryService);
  private resolverService = inject(ResolverService);
  private federationService = inject(FederationService);
  private toastService = inject(ToastService);

  public isOpen = signal(false);
  public isSpawning = signal(false);

  public stack = signal<'spring-postgres' | 'fastapi-mongo'>('spring-postgres');
  public issuerId = signal('');

  public availableSubjectTypes = signal<string[]>(['pv_module', 'battery', 'inverter', 'junction_box']);
  public selectedSubjectTypes = signal<string[]>([]);

  ngOnInit(): void {
    // Optionally load additional types from Resolver
    const resUrl = this.federationService.resolverUrl();
    if (resUrl) {
      // Logic to fetch all registered types from Resolver
    }
  }

  public open(): void {
    this.isOpen.set(true);
    this.isSpawning.set(false);
    this.issuerId.set('');
    this.selectedSubjectTypes.set([]);
  }

  public close(): void {
    if (!this.isSpawning()) {
      this.isOpen.set(false);
    }
  }

  public toggleSubjectType(type: string): void {
    this.selectedSubjectTypes.update(types =>
      types.includes(type) ? types.filter(t => t !== type) : [...types, type]
    );
  }

  public isIssuerIdValid(): boolean {
    return /^[a-z0-9-]+$/.test(this.issuerId());
  }

  public isValid(): boolean {
    return this.isIssuerIdValid() && this.selectedSubjectTypes().length > 0;
  }

  public onSubmit(): void {
    if (!this.isValid()) return;

    this.isSpawning.set(true);
    this.factoryService.spawnPlatform({
      stack: this.stack(),
      issuer_id: this.issuerId(),
      subject_types: this.selectedSubjectTypes()
    }).subscribe({
      next: (p) => {
        this.toastService.success(`Platform ${p.platform_id} spawned successfully`);
        this.federationService.refresh().subscribe();
        this.isOpen.set(false);
        this.isSpawning.set(false);
      },
      error: (err) => {
        this.toastService.error(`Failed to spawn platform: ${err.error?.message || err.message || 'Unknown error'}`);
        this.isSpawning.set(false);
      }
    });
  }
}
