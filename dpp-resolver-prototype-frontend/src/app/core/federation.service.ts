import {Injectable, inject, signal, computed, OnDestroy} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {BehaviorSubject, Observable, catchError, map, of, tap, throwError, filter} from 'rxjs';
import {environment} from '../../environments/environment';
import {FederationOverview, PlatformInfo} from './models/federation.model';
import {PollingService} from './polling.service';
import {deepEqual} from './utils/deep-equals.utils';


@Injectable({
  providedIn: 'root'
})
export class FederationService implements OnDestroy {
  private http = inject(HttpClient);
  private pollingService = inject(PollingService);
  private factoryUrl = environment.factoryUrl;

  private overviewSubject = new BehaviorSubject<FederationOverview | null>(null);
  public overview$ = this.overviewSubject.asObservable();

  private _overview = signal<FederationOverview | null>(null);
  public federation = this._overview.asReadonly();
  public platforms = computed(() => this._overview()?.platforms ?? []);
  public resolverUrl = computed(() => this._overview()?.resolver?.external_url);

  private _error = signal<string | null>(null);
  public error = this._error.asReadonly();

  private unregisterPolling: () => void;

  constructor() {
    this.unregisterPolling = this.pollingService.register(() => {
      this.refresh().subscribe({
        next: () => this.pollingService.reportSuccess(),
        error: () => this.pollingService.reportError()
      });
    });
  }

  ngOnDestroy(): void {
    this.unregisterPolling();
  }

  discover(): Observable<FederationOverview> {
    if (this.overviewSubject.value) {
      return of(this.overviewSubject.value);
    }
    return this.refresh();
  }

  refresh(): Observable<FederationOverview> {
    this._error.set(null);
    return this.http.get<FederationOverview>(`${this.factoryUrl}/federation`).pipe(
      filter(overview => overviewChanged(this._overview(), overview)),
      tap(overview => {
        this.overviewSubject.next(overview);
        this._overview.set(overview);
      }),
      catchError(err => {
        const errorMessage = `Failed to connect to Factory at ${this.factoryUrl}`;
        this._error.set(errorMessage);
        return throwError(() => err);
      })
    );
  }

  getResolverUrl(): Observable<string | undefined> {
    return this.overview$.pipe(
      map(overview => overview?.resolver?.external_url)
    );
  }

  getPlatformById(id: string): Observable<PlatformInfo | undefined> {
    return this.overview$.pipe(
      map(overview => overview?.platforms.find(p => p.platform_id === id))
    );
  }

  getAllPlatforms(): Observable<PlatformInfo[]> {
    return this.overview$.pipe(
      map(overview => overview?.platforms ?? [])
    );
  }
}

function overviewChanged(currentOverview: FederationOverview | null, newOverview: FederationOverview): boolean {
  if (!currentOverview) {
    return !!newOverview;
  }

  return !deepEqual(currentOverview, newOverview);
}

