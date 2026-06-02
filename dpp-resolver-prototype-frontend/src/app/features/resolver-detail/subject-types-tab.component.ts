import {CommonModule} from '@angular/common';
import {Component, inject, signal} from '@angular/core';
import {MatButtonModule} from '@angular/material/button';
import {MatCardModule} from '@angular/material/card';
import {MatChipsModule} from '@angular/material/chips';
import {MatDialog} from '@angular/material/dialog';
import {MatIconModule} from '@angular/material/icon';
import {MatListModule} from '@angular/material/list';
import {MatProgressBarModule} from '@angular/material/progress-bar';
import {MatTableModule} from '@angular/material/table';
import {MatTooltipModule} from '@angular/material/tooltip';
import {finalize, forkJoin, take} from 'rxjs';
import {FederationService} from '../../core/federation.service';
import {ResolverService} from '../../core/resolver.service';
import {ResolverPlatformMapping, SchemaInfo, SubjectTypeInfo} from '../../core/models/api.model';
import {toErrorMessage} from '../../core/http-error.utils';
import {SchemaDialogComponent, SchemaDialogData} from './schema-dialog/schema-dialog.component';

@Component({
  selector: 'app-resolver-subject-types-tab',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatListModule,
    MatProgressBarModule,
    MatTableModule,
    MatTooltipModule
  ],
  templateUrl: './subject-types-tab.component.html',
  styleUrl: './subject-types-tab.component.scss'
})
export class SubjectTypesTabComponent {
  private federationService = inject(FederationService);
  private resolverService = inject(ResolverService);
  private dialog = inject(MatDialog);

  public subjectTypes = signal<SubjectTypeInfo[]>([]);
  public selectedSubjectType = signal<string | null>(null);
  public schemas = signal<SchemaInfo[]>([]);
  public mappings = signal<ResolverPlatformMapping[]>([]);
  public loading = signal(false);
  public detailLoading = signal(false);
  public error = signal<string | null>(null);
  public detailError = signal<string | null>(null);
  public schemaColumns = ['version', 'published', 'actions'];
  public mappingColumns = ['platform', 'issuer', 'resolution'];

  constructor() {
    this.federationService.discover().pipe(take(1)).subscribe({
      next: () => this.loadSubjectTypes(),
      error: err => this.error.set(toErrorMessage(err, 'Failed to discover resolver'))
    });
  }

  public selectSubjectType(subjectType: string): void {
    this.selectedSubjectType.set(subjectType);
    this.loadDetail(subjectType);
  }

  public openSchema(schema: SchemaInfo): void {
    const resolverUrl = this.federationService.resolverUrl();
    const subjectType = this.selectedSubjectType();
    if (!resolverUrl || !subjectType) {
      return;
    }

    this.dialog.open<SchemaDialogComponent, SchemaDialogData, boolean>(SchemaDialogComponent, {
      autoFocus: 'first-tabbable',
      data: {mode: 'view', resolverUrl, subjectType, baseSchema: schema},
      maxWidth: 'calc(100vw - 2rem)',
      width: '62rem'
    });
  }

  public openNewSchema(): void {
    const resolverUrl = this.federationService.resolverUrl();
    const subjectType = this.selectedSubjectType();
    if (!resolverUrl || !subjectType) {
      return;
    }

    this.dialog.open<SchemaDialogComponent, SchemaDialogData, boolean>(SchemaDialogComponent, {
      autoFocus: 'first-tabbable',
      data: {mode: 'create', resolverUrl, subjectType, baseSchema: this.schemas().at(-1) ?? null},
      maxWidth: 'calc(100vw - 2rem)',
      width: '62rem'
    }).afterClosed().pipe(take(1)).subscribe(saved => {
      if (saved) {
        this.loadDetail(subjectType);
      }
    });
  }

  public schemaVersion(schema: SchemaInfo): string {
    return `${schema.major}.${schema.minor}`;
  }

  private loadSubjectTypes(): void {
    const resolverUrl = this.federationService.resolverUrl();
    if (!resolverUrl) {
      this.error.set('Resolver URL is not available.');
      return;
    }

    this.loading.set(true);
    this.error.set(null);
    this.resolverService.listSubjectTypes(resolverUrl).pipe(
      take(1),
      finalize(() => this.loading.set(false))
    ).subscribe({
      next: subjectTypes => {
        this.subjectTypes.set(subjectTypes);
        const selected = this.selectedSubjectType() ?? subjectTypes[0]?.name ?? null;
        this.selectedSubjectType.set(selected);
        if (selected) {
          this.loadDetail(selected);
        }
      },
      error: err => this.error.set(toErrorMessage(err, 'Failed to load subject types'))
    });
  }

  private loadDetail(subjectType: string): void {
    const resolverUrl = this.federationService.resolverUrl();
    if (!resolverUrl) {
      return;
    }

    this.detailLoading.set(true);
    this.detailError.set(null);
    forkJoin({
      schemas: this.resolverService.listSchemasForSubjectType(resolverUrl, subjectType),
      mappings: this.resolverService.listPlatformMappings(resolverUrl, subjectType)
    }).pipe(
      take(1),
      finalize(() => this.detailLoading.set(false))
    ).subscribe({
      next: result => {
        this.schemas.set(result.schemas);
        this.mappings.set(result.mappings);
      },
      error: err => this.detailError.set(toErrorMessage(err, `Failed to load ${subjectType}`))
    });
  }
}
