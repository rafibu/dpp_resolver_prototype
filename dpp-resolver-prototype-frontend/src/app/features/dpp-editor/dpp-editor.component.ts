import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { PlatformService } from '../../core/platform.service';
import { FederationService } from '../../core/federation.service';
import { ResolverService } from '../../core/resolver.service';
import { ToastService } from '../../core/toast.service';
import { DppDetail, DppRevision } from '../../core/models/api.model';
import { FormsModule } from '@angular/forms';
import { MonacoEditorModule } from 'ngx-monaco-editor-v2';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import { canonicalize, sha256 } from '../../core/utils/crypto.utils';

@Component({
  selector: 'app-dpp-editor',
  standalone: true,
  imports: [CommonModule, FormsModule, MonacoEditorModule, RouterLink],
  templateUrl: './dpp-editor.component.html',
  styleUrl: './dpp-editor.component.scss'
})
export class DppEditorComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private platformService = inject(PlatformService);
  private federationService = inject(FederationService);
  private resolverService = inject(ResolverService);
  private toastService = inject(ToastService);

  public platformId = signal<string | null>(null);
  public dppId = signal<string | null>(null);
  public version = signal<number | null>(null);

  public dpp = signal<DppDetail | null>(null);
  public currentRevision = signal<DppRevision | null>(null);

  public editorOptions = { theme: 'vs-light', language: 'json', readOnly: true };
  public code = signal<string>('');
  public isEditable = signal(false);

  public validationErrors = signal<any[]>([]);
  public hashVerification = signal<'success' | 'failure' | null>(null);

  private ajv = new Ajv();

  constructor() {
    addFormats(this.ajv);
  }

  ngOnInit(): void {
    this.route.params.subscribe(params => {
      this.platformId.set(params['id']);
      this.dppId.set(params['dppId']);
      this.version.set(params['version'] ? +params['version'] : null);
      this.loadData();
    });
  }

  private loadData(): void {
    const pId = this.platformId();
    const dId = this.dppId();
    if (!pId || !dId) return;

    this.federationService.getPlatformById(pId).subscribe(p => {
      if (!p) return;
      this.platformService.getDpp(p.external_url, dId).subscribe(detail => {
        this.dpp.set(detail);
        const v = this.version();
        const rev = v ? detail.revisions.find(r => r.version === v) : detail.revisions[detail.revisions.length - 1];
        if (rev) {
          this.currentRevision.set(rev);
          this.code.set(JSON.stringify(rev.payload, null, 2));
          this.hashVerification.set(null);
        }
      });
    });
  }

  public async verifyHash(): Promise<void> {
    const rev = this.currentRevision();
    if (!rev) return;

    const jcs = canonicalize(rev.payload);
    const hash = await sha256(jcs);

    if (hash === rev.hash) {
      this.hashVerification.set('success');
      this.toastService.success('Hash verified successfully!');
    } else {
      this.hashVerification.set('failure');
      this.toastService.error('Hash verification failed!');
    }
  }

  public onRevise(): void {
    this.isEditable.set(true);
    this.editorOptions = { ...this.editorOptions, readOnly: false };
    this.validate();
  }

  public onCodeChange(newCode: string): void {
    this.code.set(newCode);
    this.validate();
  }

  private async validate(): Promise<void> {
    const rev = this.currentRevision();
    if (!rev) return;

    try {
      const payload = JSON.parse(this.code());
      const resUrl = this.federationService.resolverUrl();
      if (!resUrl) return;

      // Extract type and version from schema_ref (e.g. pv_module/1.0)
      const [type, version] = rev.schema_ref.split('/');
      const [major, minor] = version.split('.');

      this.resolverService.getSchema(resUrl, type, +major, +minor).subscribe(schema => {
        const validate = this.ajv.compile(schema);
        const valid = validate(payload);
        this.validationErrors.set(valid ? [] : (validate.errors || []));
      });
    } catch (e) {
      this.validationErrors.set([{ message: 'Invalid JSON' }]);
    }
  }

  public onSubmit(): void {
    const pId = this.platformId();
    const dId = this.dppId();
    const rev = this.currentRevision();
    if (!pId || !dId || !rev) return;

    try {
      const payload = JSON.parse(this.code());
      const [schemaType, schemaVer] = rev.schema_ref.split('/');
      const [major, minor] = schemaVer.split('.').map(Number);
      this.federationService.getPlatformById(pId).subscribe(p => {
        if (!p) return;
        this.platformService.reviseDpp(p.external_url, dId, {
          schema_version: { subject_type: schemaType, major_version: major, minor_version: minor },
          dpp_payload: payload
        }).subscribe({
          next: () => {
            this.toastService.success('Revision submitted successfully');
            this.router.navigate(['/platforms', pId, 'dpps']);
          },
          error: (err) => this.toastService.error(`Failed to revise: ${err.message || 'Unknown error'}`)
        });
      });
    } catch (e) {
      this.toastService.error('Invalid JSON payload');
    }
  }
}
