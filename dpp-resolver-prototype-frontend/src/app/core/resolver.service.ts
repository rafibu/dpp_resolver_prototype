import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {Observable} from 'rxjs';
import {map} from 'rxjs/operators';
import {PublishSchemaRequest, ResolverPlatformMapping, SchemaInfo, SubjectTypeInfo} from './models/api.model';

@Injectable({
  providedIn: 'root'
})
export class ResolverService {
  private http = inject(HttpClient);

  getSchema(resolverUrl: string, subjectType: string, major: number, minor: number): Observable<any> {
    return this.http.get<any>(`${resolverUrl}/schemas/${subjectType}/${major}/${minor}`).pipe(
      map(dto => dto?.schema_document ?? dto?.schemaDocument ?? dto)
    );
  }

  listSchemasForSubjectType(resolverUrl: string, subjectType: string): Observable<SchemaInfo[]> {
    return this.http.get<any[]>(`${resolverUrl}/schemas/${subjectType}`).pipe(
      map(dtos => (dtos ?? []).map(dto => normalizeSchemaInfo(dto)).sort(compareSchemaInfo))
    );
  }

  publishSchema(resolverUrl: string, request: PublishSchemaRequest): Observable<SchemaInfo> {
    return this.http.post<any>(`${resolverUrl}/schemas`, request).pipe(
      map(dto => normalizeSchemaInfo(dto))
    );
  }

  listSubjectTypes(resolverUrl: string): Observable<SubjectTypeInfo[]> {
    return this.http.get<any[]>(`${resolverUrl}/admin/subject-types`).pipe(
      map(dtos => (dtos ?? []).map(dto => ({
        name: dto.name,
        description: dto.description
      })).sort((a, b) => a.name.localeCompare(b.name)))
    );
  }

  listPlatformMappings(resolverUrl: string, subjectType?: string): Observable<ResolverPlatformMapping[]> {
    const suffix = subjectType ? `/${subjectType}` : '';
    return this.http.get<any[]>(`${resolverUrl}/admin/platforms${suffix}`).pipe(
      map(dtos => (dtos ?? []).map(dto => ({
        platform: dto.platform,
        issuer_id: dto.issuerId ?? dto.issuer_id,
        resolution_url: dto.resolutionUrl ?? dto.resolution_url,
        subject_types: dto.subjectTypes ?? dto.subject_types ?? []
      })).sort((a, b) => a.platform.localeCompare(b.platform)))
    );
  }
}

function normalizeSchemaInfo(dto: any): SchemaInfo {
  return {
    subject_type: dto.subjectType ?? dto.subject_type,
    major: dto.majorVersion ?? dto.major_version,
    minor: dto.minorVersion ?? dto.minor_version,
    schema: dto.schemaDocument ?? dto.schema_document,
    published_at: dto.publishedAt ?? dto.published_at
  };
}

function compareSchemaInfo(a: SchemaInfo, b: SchemaInfo): number {
  return (a.major - b.major) || (a.minor - b.minor);
}
