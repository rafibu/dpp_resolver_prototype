import {Component, computed, DestroyRef, inject, signal} from '@angular/core';
import {CommonModule} from '@angular/common';
import {FormsModule} from '@angular/forms';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {ActivatedRoute, Router, RouterLink} from '@angular/router';
import {MatButtonModule} from '@angular/material/button';
import {MatCardModule} from '@angular/material/card';
import {MatChipsModule} from '@angular/material/chips';
import {MatIconModule} from '@angular/material/icon';
import {MatListModule} from '@angular/material/list';
import {MatProgressBarModule} from '@angular/material/progress-bar';
import {MonacoEditorModule} from 'ngx-monaco-editor-v2';
import {combineLatest, finalize, take} from 'rxjs';
import {PlatformService} from '../../core/platform.service';
import {FederationService} from '../../core/federation.service';
import {ResolverService} from '../../core/resolver.service';
import {ToastService} from '../../core/toast.service';
import {DppDetail, DppRevision} from '../../core/models/api.model';
import {canonicalize, sha256} from '../../core/utils/crypto.utils';
import {toErrorMessage} from '../../core/http-error.utils';
import {
  createJsonSchemaValidator,
  JsonValidationIssue,
  validateJsonPayload
} from '../../core/utils/json-schema-validator.utils';

@Component({
  selector: 'app-dpp-editor',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MonacoEditorModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatListModule,
    MatProgressBarModule
  ],
  templateUrl: './dpp-editor.component.html',
  styleUrl: './dpp-editor.component.scss'
})
export class DppEditorComponent {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private platformService = inject(PlatformService);
  private federationService = inject(FederationService);
  private resolverService = inject(ResolverService);
  private toastService = inject(ToastService);
  private destroyRef = inject(DestroyRef);

  public platformId = signal<string | null>(null);
  public dppId = signal<string | null>(null);
  public version = signal<number | null>(null);
  public mode = signal<string | null>(null);
  public dpp = signal<DppDetail | null>(null);
  public currentRevision = signal<DppRevision | null>(null);
  public editorOptions = signal({
    theme: 'vs-light',
    language: 'json',
    readOnly: true,
    minimap: { enabled: false },
    automaticLayout: true,
    scrollBeyondLastLine: false
  });
  public code = signal<string>('');
  public isEditable = signal(false);
  public loading = signal(false);
  public saving = signal(false);
  public error = signal<string | null>(null);
  public validationErrors = signal<JsonValidationIssue[]>([]);
  public hashVerification = signal<'success' | 'failure' | null>(null);
  public canSubmit = computed(() => this.isEditable() && !this.saving() && this.validationErrors().length === 0);

  private ajv = createJsonSchemaValidator();

  constructor() {
    combineLatest([this.route.paramMap, this.route.queryParamMap]).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(([params, query]) => {
      this.platformId.set(params.get('id'));
      this.dppId.set(params.get('dppId'));
      const version = params.get('version');
      this.version.set(version ? Number(version) : null);
      this.mode.set(query.get('mode'));
      this.loadData();
    });
  }

  public async verifyHash(): Promise<void> {
    const rev = this.currentRevision();
    if (!rev) {
      return;
    }

    const hash = await sha256(canonicalize(rev.payload));
    if (hash === rev.hash) {
      this.hashVerification.set('success');
      this.toastService.success('Hash verified successfully');
    } else {
      this.hashVerification.set('failure');
      this.toastService.error('Hash verification failed');
    }
  }

  public onRevise(): void {
    this.setEditable(true);
    this.validate();
  }

  public cancelEdit(): void {
    const revision = this.currentRevision();
    this.setEditable(false);
    this.validationErrors.set([]);
    if (revision) {
      this.code.set(JSON.stringify(revision.payload, null, 2));
    }
  }

  public onCodeChange(newCode: string): void {
    this.code.set(newCode);
    this.validate();
  }

  public onSubmit(): void {
    const pId = this.platformId();
    const dId = this.dppId();
    const rev = this.currentRevision();
    if (!pId || !dId || !rev || !this.canSubmit()) {
      return;
    }

    try {
      const payload = JSON.parse(this.code());
      const [schemaType, schemaVer] = rev.schema_ref.split('/');
      const [major, minor] = schemaVer.split('.').map(Number);
      const platform = this.federationService.platforms().find(p => p.platform_id === pId);
      if (!platform) {
        this.toastService.error(`Platform ${pId} is not in the current federation snapshot`);
        return;
      }

      this.saving.set(true);
      this.platformService.reviseDpp(platform.external_url, dId, {
        schema_version: { subject_type: schemaType, major_version: major, minor_version: minor },
        dpp_payload: payload
      }).pipe(
        take(1),
        finalize(() => this.saving.set(false))
      ).subscribe({
        next: () => {
          this.toastService.success('Revision submitted successfully');
          void this.router.navigate(['/platforms', pId, 'dpps']);
        },
        error: err => this.toastService.error(toErrorMessage(err, 'Failed to submit revision'))
      });
    } catch {
      this.toastService.error('Invalid JSON payload');
    }
  }

  private loadData(): void {
    const pId = this.platformId();
    const dId = this.dppId();
    if (!pId || !dId) {
      return;
    }

    const platform = this.federationService.platforms().find(p => p.platform_id === pId);
    if (!platform) {
      this.error.set(`Platform ${pId} is not in the current federation snapshot.`);
      return;
    }

    this.loading.set(true);
    this.error.set(null);
    this.platformService.getDpp(platform.external_url, dId).pipe(
      take(1),
      finalize(() => this.loading.set(false))
    ).subscribe({
      next: detail => {
        this.dpp.set(detail);
        const selectedVersion = this.version();
        const revision = selectedVersion
          ? detail.revisions.find(r => r.version === selectedVersion)
          : detail.revisions.at(-1);
        if (revision) {
          this.currentRevision.set(revision);
          this.code.set(JSON.stringify(revision.payload, null, 2));
          this.hashVerification.set(null);
          this.validationErrors.set([]);
          this.setEditable(this.mode() === 'revise');
          if (this.mode() === 'revise') {
            this.validate();
          }
        }
      },
      error: err => this.error.set(toErrorMessage(err, `Failed to load ${dId}`))
    });
  }

  private validate(): void {
    const rev = this.currentRevision();
    const resolverUrl = this.federationService.resolverUrl();
    if (!rev || !resolverUrl) {
      return;
    }

    try {
      const payload = JSON.parse(this.code());
      const [type, version] = rev.schema_ref.split('/');
      const [major, minor] = version.split('.');

      this.resolverService.getSchema(resolverUrl, type, Number(major), Number(minor)).pipe(take(1)).subscribe({
        next: schema => {
          this.validationErrors.set(validateJsonPayload(this.ajv, schema, payload));
        },
        error: err => this.validationErrors.set([{
          instancePath: '',
          message: toErrorMessage(err, 'Could not load schema'),
          params: {}
        }])
      });
    } catch {
      this.validationErrors.set([{ instancePath: '', message: 'Invalid JSON', params: {} }]);
    }
  }

  private setEditable(isEditable: boolean): void {
    this.isEditable.set(isEditable);
    this.editorOptions.update(options => ({ ...options, readOnly: !isEditable }));
  }
}
