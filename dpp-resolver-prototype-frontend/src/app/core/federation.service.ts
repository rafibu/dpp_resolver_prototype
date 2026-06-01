import {computed, DestroyRef, inject, Injectable, signal} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {BehaviorSubject, catchError, map, Observable, of, tap, throwError} from 'rxjs';
import {environment} from '../../environments/environment';
import {FederationOverview, PlatformInfo} from './models/federation.model';
import {PollingService} from './polling.service';
import {deepEqual} from './utils/deep-equals.utils';
import {toErrorMessage} from './http-error.utils';


@Injectable({
  providedIn: 'root'
})
export class FederationService {
  private http = inject(HttpClient);
  private pollingService = inject(PollingService);
  private destroyRef = inject(DestroyRef);
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

    this.destroyRef.onDestroy(() => this.unregisterPolling());
  }

  discover(): Observable<FederationOverview> {
    if (this.overviewSubject.value) {
      return of(this.overviewSubject.value);
    }
    return this.refresh();
  }

  refresh(): Observable<FederationOverview> {
    return this.http.get<FederationOverview>(`${this.factoryUrl}/federation`).pipe(
      tap(overview => {
        this._error.set(null);
        if (overviewChanged(this._overview(), overview)) {
          this.overviewSubject.next(overview);
          this._overview.set(overview);
        }
      }),
      catchError(err => {
        const errorMessage = toErrorMessage(err, `Failed to connect to Factory at ${this.factoryUrl}`);
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
