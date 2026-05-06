import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { SpawnSpec, LogLine, ScenarioResult, ScenarioStatus } from './models/api.model';
import { PlatformInfo } from './models/federation.model';

@Injectable({
  providedIn: 'root'
})
export class FactoryService {
  private http = inject(HttpClient);
  private factoryUrl = environment.factoryUrl;

  getPlatforms(): Observable<PlatformInfo[]> {
    return this.http.get<PlatformInfo[]>(`${this.factoryUrl}/platforms`);
  }

  getPlatform(id: string): Observable<PlatformInfo> {
    return this.http.get<PlatformInfo>(`${this.factoryUrl}/platforms/${id}`);
  }

  spawnPlatform(spec: SpawnSpec): Observable<PlatformInfo> {
    return this.http.post<PlatformInfo>(`${this.factoryUrl}/platforms`, spec);
  }

  pausePlatform(id: string): Observable<void> {
    return this.http.post<void>(`${this.factoryUrl}/platforms/${id}/pause`, {});
  }

  resumePlatform(id: string): Observable<void> {
    return this.http.post<void>(`${this.factoryUrl}/platforms/${id}/resume`, {});
  }

  resetPlatform(id: string): Observable<void> {
    return this.http.post<void>(`${this.factoryUrl}/platforms/${id}/reset`, {});
  }

  deletePlatform(id: string): Observable<void> {
    return this.http.delete<void>(`${this.factoryUrl}/platforms/${id}`);
  }

  getPlatformLogs(id: string, lines: number = 200): Observable<LogLine[]> {
    const params = new HttpParams().set('lines', lines.toString());
    return this.http.get<LogLine[]>(`${this.factoryUrl}/platforms/${id}/logs`, { params });
  }

  runScenario(id: 's1' | 's2'): Observable<ScenarioResult> {
    return this.http.post<ScenarioResult>(`${this.factoryUrl}/scenarios/${id}`, {});
  }

  getScenarioStatus(id: 's1' | 's2'): Observable<ScenarioStatus> {
    return this.http.get<ScenarioStatus>(`${this.factoryUrl}/scenarios/${id}/status`);
  }
}
