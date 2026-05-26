import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { SchemaInfo } from './models/api.model';

@Injectable({
  providedIn: 'root'
})
export class ResolverService {
  private http = inject(HttpClient);

  getSchema(resolverUrl: string, subjectType: string, major: number, minor: number): Observable<any> {
    return this.http.get<any>(`${resolverUrl}/schemas/${subjectType}/${major}/${minor}`).pipe(
      map(dto => dto?.schemaDocument ?? dto)
    );
  }

  listSchemasForSubjectType(resolverUrl: string, subjectType: string): Observable<SchemaInfo[]> {
    return this.http.get<any[]>(`${resolverUrl}/schemas/${subjectType}`).pipe(
      map(dtos => (dtos ?? []).map(dto => ({
        subject_type: dto.subjectType ?? dto.subject_type,
        major: dto.majorVersion ?? dto.major_version,
        minor: dto.minorVersion ?? dto.minor_version,
        schema: dto.schemaDocument ?? dto.schema_document
      })))
    );
  }
}
