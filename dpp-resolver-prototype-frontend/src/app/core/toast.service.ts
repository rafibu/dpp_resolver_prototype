import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info';
}

@Injectable({
  providedIn: 'root'
})
export class ToastService {
  private _toasts = signal<Toast[]>([]);
  public toasts = this._toasts.asReadonly();
  private nextId = 0;

  show(message: string, type: 'success' | 'error' | 'info' = 'info') {
    const id = this.nextId++;
    const toast: Toast = { id, message, type };
    this._toasts.update(t => [...t, toast]);

    setTimeout(() => {
      this.remove(id);
    }, 5000);
  }

  success(message: string) { this.show(message, 'success'); }
  error(message: string) { this.show(message, 'error'); }

  remove(id: number) {
    this._toasts.update(t => t.filter(x => x.id !== id));
  }
}
