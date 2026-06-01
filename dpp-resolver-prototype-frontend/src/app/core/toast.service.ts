import { Injectable, inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

export interface Toast {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info';
}

@Injectable({
  providedIn: 'root'
})
export class ToastService {
  private snackBar = inject(MatSnackBar);

  show(message: string, type: 'success' | 'error' | 'info' = 'info') {
    this.snackBar.open(message, 'Dismiss', {
      duration: type === 'error' ? 8000 : 4500,
      horizontalPosition: 'end',
      verticalPosition: 'bottom',
      panelClass: [`snack-${type}`]
    });
  }

  success(message: string) { this.show(message, 'success'); }
  error(message: string) { this.show(message, 'error'); }
}
