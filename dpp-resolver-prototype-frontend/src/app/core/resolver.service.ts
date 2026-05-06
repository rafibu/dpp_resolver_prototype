import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { SchemaInfo } from './models/api.model';

@Injectable({
  providedIn: 'root'
})
export class ResolverService {
  private http = inject(HttpClient);

  getSchema(resolverUrl: string, subjectType: string, major: number, minor: number): Observable<any> {
    return this.http.get<any>(`${resolverUrl}/schemas/${subjectType}/${major}.${minor}`);
  }

  listSchemasForSubjectType(resolverUrl: string, subjectType: string): Observable<SchemaInfo[]> {
    return this.http.get<SchemaInfo[]>(`${resolverUrl}/schemas/${subjectType}`);
  }
}
