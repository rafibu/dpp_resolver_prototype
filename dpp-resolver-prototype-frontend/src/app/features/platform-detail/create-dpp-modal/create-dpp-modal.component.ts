import {Component, computed, inject, signal} from '@angular/core';
import {CommonModule} from '@angular/common';
import {FormsModule} from '@angular/forms';
import {MatButtonModule} from '@angular/material/button';
import {MAT_DIALOG_DATA, MatDialogModule, MatDialogRef} from '@angular/material/dialog';
import {MatFormFieldModule} from '@angular/material/form-field';
import {MatIconModule} from '@angular/material/icon';
import {MatInputModule} from '@angular/material/input';
import {MatListModule} from '@angular/material/list';
import {MatProgressBarModule} from '@angular/material/progress-bar';
import {MatSelectModule} from '@angular/material/select';
import {MonacoEditorModule} from 'ngx-monaco-editor-v2';
import {finalize, take} from 'rxjs';
import {PlatformService} from '../../../core/platform.service';
import {ResolverService} from '../../../core/resolver.service';
import {FederationService} from '../../../core/federation.service';
import {ToastService} from '../../../core/toast.service';
import {SchemaInfo} from '../../../core/models/api.model';
import {toErrorMessage} from '../../../core/http-error.utils';
import {createEmptyPayloadFromSchema} from '../../../core/utils/json-schema-skeleton.utils';
import {
  createJsonSchemaValidator,
  JsonValidationIssue,
  validateJsonPayload
} from '../../../core/utils/json-schema-validator.utils';

export interface CreateDppDialogData {
  platformId: string;
  platformUrl: string;
  issuerId: string;
  subjectTypes: string[];
}

@Component({
  selector: 'app-create-dpp-modal',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MonacoEditorModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatListModule,
    MatProgressBarModule,
    MatSelectModule
  ],
  templateUrl: './create-dpp-modal.component.html',
  styleUrl: './create-dpp-modal.component.scss'
})
export class CreateDppModalComponent {
  private platformService = inject(PlatformService);
  private resolverService = inject(ResolverService);
  private federationService = inject(FederationService);
  private toastService = inject(ToastService);
  private dialogRef = inject(MatDialogRef<CreateDppModalComponent, boolean>);
  public data = inject<CreateDppDialogData>(MAT_DIALOG_DATA);

  public selectedSubjectType = signal(this.data.subjectTypes[0] || '');
  public schemas = signal<SchemaInfo[]>([]);
  public selectedSchema = signal<SchemaInfo | null>(null);
  public schemaLoading = signal(false);
  public schemaError = signal<string | null>(null);
  public isSubmitting = signal(false);
  public editorOptions = {
    theme: 'vs-light',
    language: 'json',
    readOnly: false,
    minimap: { enabled: false },
    automaticLayout: true,
    scrollBeyondLastLine: false
  };
  public code = signal<string>('{\n  \n}');
  public validationErrors = signal<JsonValidationIssue[]>([]);
  public canSubmit = computed(() =>
    !this.isSubmitting() &&
    !!this.selectedSchema() &&
    this.validationErrors().length === 0
  );

  private ajv = createJsonSchemaValidator();

  constructor() {
    this.loadSchemas();
  }

  public close(): void {
    if (!this.isSubmitting()) {
      this.dialogRef.close(false);
    }
  }

  public onSubjectTypeChange(type: string): void {
    this.selectedSubjectType.set(type);
    this.loadSchemas();
  }

  public onSchemaChange(schema: SchemaInfo): void {
    this.selectedSchema.set(schema);
    this.code.set(JSON.stringify(this.createPayloadSkeleton(schema), null, 2));
    this.validate();
  }

  public onCodeChange(newCode: string): void {
    this.code.set(newCode);
    this.validate();
  }

  public onSubmit(): void {
    const schema = this.selectedSchema();
    if (!schema || !this.canSubmit()) {
      return;
    }

    try {
      const payload = JSON.parse(this.code());
      this.isSubmitting.set(true);
      this.platformService.issueDpp(this.data.platformUrl, {
        schema_version: {
          subject_type: schema.subject_type,
          major_version: schema.major,
          minor_version: schema.minor
        },
        dpp_payload: payload
      }).pipe(
        take(1),
        finalize(() => this.isSubmitting.set(false))
      ).subscribe({
        next: revision => {
          this.toastService.success(`DPP ${revision.dpp_id} issued successfully`);
          this.dialogRef.close(true);
        },
        error: err => {
          this.toastService.error(toErrorMessage(err, 'Failed to issue DPP'));
        }
      });
    } catch {
      this.toastService.error('Invalid JSON payload');
    }
  }

  private loadSchemas(): void {
    const resolverUrl = this.federationService.resolverUrl();
    const subjectType = this.selectedSubjectType();
    if (!resolverUrl || !subjectType) {
      this.schemas.set([]);
      this.selectedSchema.set(null);
      return;
    }

    this.schemaLoading.set(true);
    this.schemaError.set(null);
    this.resolverService.listSchemasForSubjectType(resolverUrl, subjectType).pipe(
      take(1),
      finalize(() => this.schemaLoading.set(false))
    ).subscribe({
      next: schemas => {
        this.schemas.set(schemas);
        const latest = schemas.at(-1) ?? null;
        this.selectedSchema.set(latest);
        if (latest) {
          this.code.set(JSON.stringify(this.createPayloadSkeleton(latest), null, 2));
          this.validate();
        } else {
          this.validationErrors.set([{ instancePath: '', message: 'No schema available', params: {} }]);
        }
      },
      error: err => {
        this.schemaError.set(toErrorMessage(err, 'Failed to load schemas'));
      }
    });
  }

  private validate(): void {
    const schema = this.selectedSchema();
    if (!schema) {
      return;
    }

    try {
      const payload = JSON.parse(this.code());
      this.validationErrors.set(validateJsonPayload(this.ajv, schema.schema, payload));
    } catch {
      this.validationErrors.set([{ instancePath: '', message: 'Invalid JSON', params: {} }]);
    }
  }

  private createPayloadSkeleton(schema: SchemaInfo): Record<string, unknown> {
    const skeleton = createEmptyPayloadFromSchema(schema.schema);
    return skeleton && typeof skeleton === 'object' && !Array.isArray(skeleton) ? skeleton as Record<string, unknown> : {};
  }
}
