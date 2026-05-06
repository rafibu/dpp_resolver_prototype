import { Component } from '@angular/core';
import { LogViewerComponent } from '../../log-viewer/log-viewer.component';

@Component({
  selector: 'app-logs-tab',
  standalone: true,
  imports: [LogViewerComponent],
  template: '<app-log-viewer />',
  styles: [':host { display: block; height: 100%; }']
})
export class LogsTabComponent {}
