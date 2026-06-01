import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {Observable} from 'rxjs';
import {DppDetail, DppRevisionResponse, DppSummary, IssueRequest, ReviseRequest} from './models/api.model';

@Injectable({
  providedIn: 'root'
})
export class PlatformService {
  private http = inject(HttpClient);

  listDpps(platformUrl: string): Observable<DppSummary[]> {
    return this.http.get<DppSummary[]>(`${platformUrl}/dpps`);
  }

  getDpp(platformUrl: string, dppId: string): Observable<DppDetail> {
    return this.http.get<DppDetail>(`${platformUrl}/dpps/${dppId}`);
  }

  issueDpp(platformUrl: string, request: IssueRequest): Observable<DppRevisionResponse> {
    return this.http.post<DppRevisionResponse>(`${platformUrl}/dpps/issue`, request);
  }

  reviseDpp(platformUrl: string, dppId: string, request: ReviseRequest): Observable<DppRevisionResponse> {
    return this.http.post<DppRevisionResponse>(`${platformUrl}/dpps/${dppId}/revise`, request);
  }
}
