import {Injectable, OnDestroy, signal} from '@angular/core';
import {fromEvent, interval, map, merge, Subscription} from 'rxjs';

export type PollingCallback = () => void;

@Injectable({
  providedIn: 'root'
})
export class PollingService implements OnDestroy {
  private callbacks = new Set<PollingCallback>();
  private pollSubscription?: Subscription;

  public isTabActive = signal(true);
  public lastSuccess = signal<Date | null>(null);
  public hasError = signal(false);

  constructor() {
    // Page Visibility API
    merge(
      fromEvent(document, 'visibilitychange').pipe(map(() => !document.hidden)),
      fromEvent(window, 'focus').pipe(map(() => true)),
      fromEvent(window, 'blur').pipe(map(() => false))
    ).subscribe(active => {
      this.isTabActive.set(active);
      if (active) this.start();
      else this.stop();
    });

    this.start();
  }

  ngOnDestroy(): void {
    this.stop();
  }

  public register(cb: PollingCallback): () => void {
    this.callbacks.add(cb);
    return () => this.callbacks.delete(cb);
  }

  private start(): void {
    if (this.pollSubscription) return;

    this.pollSubscription = interval(10_000).subscribe(() => {
      if (this.isTabActive()) {
        this.callbacks.forEach(cb => cb());
      }
    });
  }

  private stop(): void {
    this.pollSubscription?.unsubscribe();
    this.pollSubscription = undefined;
  }

  public reportSuccess(): void {
    this.lastSuccess.set(new Date());
    this.hasError.set(false);
  }

  public reportError(): void {
    this.hasError.set(true);
  }
}
