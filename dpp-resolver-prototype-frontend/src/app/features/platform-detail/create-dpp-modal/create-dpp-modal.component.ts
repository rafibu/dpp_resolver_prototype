import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MonacoEditorModule } from 'ngx-monaco-editor-v2';
import { PlatformService } from '../../../core/platform.service';
import { ResolverService } from '../../../core/resolver.service';
import { FederationService } from '../../../core/federation.service';
import { ToastService } from '../../../core/toast.service';
import { SchemaInfo } from '../../../core/models/api.model';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';

@Component({
  selector: 'app-create-dpp-modal',
  standalone: true,
  imports: [CommonModule, FormsModule, MonacoEditorModule],
  templateUrl: './create-dpp-modal.component.html',
  styleUrl: './create-dpp-modal.component.scss'
})
export class CreateDppModalComponent implements OnInit {
  private platformService = inject(PlatformService);
  private resolverService = inject(ResolverService);
  private federationService = inject(FederationService);
  private toastService = inject(ToastService);

  public isOpen = signal(false);
  public platformId = signal<string>('');
  public platformUrl = signal<string>('');
  public issuerId = signal<string>('');

  public dppId = signal<string>('');
  public selectedSubjectType = signal<string>('');
  public subjectTypes = signal<string[]>([]);
  public schemas = signal<SchemaInfo[]>([]);
  public selectedSchema = signal<SchemaInfo | null>(null);

  public editorOptions = { theme: 'vs-light', language: 'json', readOnly: false };
  public code = signal<string>('{\n  \n}');
  public validationErrors = signal<any[]>([]);

  private ajv = new Ajv();

  constructor() {
    addFormats(this.ajv);
  }

  ngOnInit(): void {}

  public open(platformId: string, platformUrl: string, issuerId: string, subjectTypes: string[]): void {
    this.platformId.set(platformId);
    this.platformUrl.set(platformUrl);
    this.issuerId.set(issuerId);
    this.subjectTypes.set(subjectTypes);
    this.dppId.set(`${issuerId}-`);
    this.selectedSubjectType.set(subjectTypes[0] || '');
    this.isOpen.set(true);
    this.onSubjectTypeChange();
  }

  public close(): void {
    this.isOpen.set(false);
  }

  public onSubjectTypeChange(): void {
    const resUrl = this.federationService.resolverUrl();
    if (!resUrl || !this.selectedSubjectType()) return;

    this.resolverService.listSchemasForSubjectType(resUrl, this.selectedSubjectType()).subscribe(schemas => {
      this.schemas.set(schemas);
      if (schemas.length > 0) {
        this.selectedSchema.set(schemas[schemas.length - 1]); // Default to latest
        this.onSchemaChange();
      } else {
        this.selectedSchema.set(null);
      }
    });
  }

  public onSchemaChange(): void {
    const schema = this.selectedSchema();
    if (!schema) return;

    // Pre-load minimal valid skeleton
    const skeleton: any = {
      manufacturer: "Example Corp",
      model: "Model-X",
      serial_number: "SN-12345",
      recycled_content: 10
    };

    // Add dependencies array if schema expects it
    if (schema.schema && schema.schema.properties && schema.schema.properties.dependencies) {
        skeleton.dependencies = [];
    }

    this.code.set(JSON.stringify(skeleton, null, 2));
    this.validate();
  }

  public onCodeChange(newCode: string): void {
    this.code.set(newCode);
    this.validate();
  }

  private async validate(): Promise<void> {
    const schema = this.selectedSchema();
    if (!schema) return;

    try {
      const payload = JSON.parse(this.code());
      const validate = this.ajv.compile(schema.schema);
      const valid = validate(payload);
      this.validationErrors.set(valid ? [] : (validate.errors || []));
    } catch (e) {
      this.validationErrors.set([{ message: 'Invalid JSON' }]);
    }
  }

  public onSubmit(): void {
    if (!this.dppId().startsWith(this.issuerId())) {
      this.toastService.error(`DPP ID must start with issuer prefix: ${this.issuerId()}`);
      return;
    }

    try {
      const payload = JSON.parse(this.code());
      const schema = this.selectedSchema();
      if (!schema) return;

      this.platformService.issueDpp(this.platformUrl(), {
        dpp_id: this.dppId() || undefined,
        schema_version: {
          subject_type: schema.subject_type,
          major_version: schema.major,
          minor_version: schema.minor
        },
        dpp_payload: payload
      }).subscribe({
        next: () => {
          this.toastService.success(`DPP ${this.dppId()} issued successfully`);
          this.close();
          // Emit event or refresh data - for simplicity, we'll tell the user they should refresh or rely on FE-10 polling
        },
        error: (err) => this.toastService.error(`Failed to issue DPP: ${err.error?.message || err.message || 'Unknown error'}`)
      });
    } catch (e) {
      this.toastService.error('Invalid JSON payload');
    }
  }
}
