import {CommonModule} from '@angular/common';
import {Component, computed, inject, signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {MAT_DIALOG_DATA, MatDialogModule, MatDialogRef} from '@angular/material/dialog';
import {MatButtonModule} from '@angular/material/button';
import {MatFormFieldModule} from '@angular/material/form-field';
import {MatIconModule} from '@angular/material/icon';
import {MatInputModule} from '@angular/material/input';
import {MatProgressBarModule} from '@angular/material/progress-bar';
import {MonacoEditorModule} from 'ngx-monaco-editor-v2';
import {finalize, take} from 'rxjs';
import {ResolverService} from '../../../core/resolver.service';
import {SchemaInfo} from '../../../core/models/api.model';
import {ToastService} from '../../../core/toast.service';
import {toErrorMessage} from '../../../core/http-error.utils';

export interface SchemaDialogData {
  mode: 'view' | 'create';
  resolverUrl: string;
  subjectType: string;
  baseSchema: SchemaInfo | null;
}

@Component({
  selector: 'app-schema-dialog',
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
    MatProgressBarModule
  ],
  templateUrl: './schema-dialog.component.html',
  styleUrl: './schema-dialog.component.scss'
})
export class SchemaDialogComponent {
  private resolverService = inject(ResolverService);
  private toastService = inject(ToastService);
  private dialogRef = inject(MatDialogRef<SchemaDialogComponent, boolean>);
  public data = inject<SchemaDialogData>(MAT_DIALOG_DATA);

  public major = signal(this.data.baseSchema ? this.data.baseSchema.major : 1);
  public minor = signal(this.data.mode === 'create' && this.data.baseSchema ? this.data.baseSchema.minor + 1 : this.data.baseSchema?.minor ?? 0);
  public code = signal(JSON.stringify(this.initialDocument(), null, 2));
  public isSubmitting = signal(false);
  public jsonError = signal<string | null>(null);
  public editorOptions = computed(() => ({
    theme: 'vs-light',
    language: 'json',
    readOnly: this.data.mode === 'view' || this.isSubmitting(),
    minimap: {enabled: false}
  }));
  public title = computed(() => this.data.mode === 'view'
    ? `${this.data.subjectType}/${this.major()}.${this.minor()}`
    : `New ${this.data.subjectType} schema`);
  public canPublish = computed(() =>
    this.data.mode === 'create' &&
    !this.isSubmitting() &&
    this.major() >= 1 &&
    this.minor() >= 0 &&
    !this.jsonError()
  );

  public onVersionChange(): void {
    if (this.data.mode !== 'create') {
      return;
    }
    try {
      const document = JSON.parse(this.code());
      document['$id'] = this.schemaId();
      this.code.set(JSON.stringify(document, null, 2));
      this.jsonError.set(null);
    } catch {
      this.jsonError.set('Schema JSON is invalid');
    }
  }

  public onCodeChange(value: string): void {
    this.code.set(value);
    try {
      JSON.parse(value);
      this.jsonError.set(null);
    } catch {
      this.jsonError.set('Schema JSON is invalid');
    }
  }

  public publish(): void {
    if (!this.canPublish()) {
      return;
    }

    try {
      const schemaDocument = JSON.parse(this.code());
      schemaDocument['$id'] = this.schemaId();
      this.isSubmitting.set(true);
      this.resolverService.publishSchema(this.data.resolverUrl, {
        subject_type: this.data.subjectType,
        major_version: this.major(),
        minor_version: this.minor(),
        schema_document: schemaDocument
      }).pipe(
        take(1),
        finalize(() => this.isSubmitting.set(false))
      ).subscribe({
        next: schema => {
          this.toastService.success(`Published ${schema.subject_type}/${schema.major}.${schema.minor}`);
          this.dialogRef.close(true);
        },
        error: err => this.toastService.error(toErrorMessage(err, 'Failed to publish schema'))
      });
    } catch {
      this.jsonError.set('Schema JSON is invalid');
    }
  }

  public close(): void {
    if (!this.isSubmitting()) {
      this.dialogRef.close(false);
    }
  }

  private initialDocument(): unknown {
    if (this.data.baseSchema) {
      const document = clone(this.data.baseSchema.schema);
      if (this.data.mode === 'create' && document && typeof document === 'object') {
        (document as Record<string, unknown>)['$id'] = this.schemaId();
      }
      return document;
    }

    return {
      '$schema': 'https://json-schema.org/draft/2020-12/schema',
      '$id': this.schemaId(),
      title: this.data.subjectType,
      type: 'object',
      properties: {},
      required: []
    };
  }

  private schemaId(): string {
    return `https://schemas.dpp.eu/${this.data.subjectType}/${this.major()}.${this.minor()}`;
  }
}

function clone(value: unknown): unknown {
  return typeof structuredClone === 'function'
    ? structuredClone(value)
    : JSON.parse(JSON.stringify(value));
}
