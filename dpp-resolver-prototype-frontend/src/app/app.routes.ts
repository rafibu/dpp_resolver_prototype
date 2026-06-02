import {Routes} from '@angular/router';
import {FederationMapComponent} from './features/federation-map/federation-map.component';

export const routes: Routes = [
  { path: '', component: FederationMapComponent },
  { path: 'scenarios', loadComponent: () => import('./features/scenario-runner/scenario-runner.component').then(m => m.ScenarioRunnerComponent) },
  {
    path: 'resolver',
    loadComponent: () => import('./features/resolver-detail/resolver-detail.component').then(m => m.ResolverDetailComponent),
    children: [
      { path: 'subject-types', loadComponent: () => import('./features/resolver-detail/subject-types-tab.component').then(m => m.SubjectTypesTabComponent) },
      {
        path: 'logs',
        loadComponent: () => import('./features/log-viewer/log-viewer.component').then(m => m.LogViewerComponent),
        data: { logSource: 'resolver' }
      },
      { path: '', redirectTo: 'subject-types', pathMatch: 'full' }
    ]
  },
  {
    path: 'platforms/:id',
    loadComponent: () => import('./features/platform-detail/platform-detail.component').then(m => m.PlatformDetailComponent),
    children: [
      { path: 'dpps', loadComponent: () => import('./features/platform-detail/tabs/dpps-tab.component').then(m => m.DppsTabComponent) },
      { path: 'logs', loadComponent: () => import('./features/platform-detail/tabs/logs-tab.component').then(m => m.LogsTabComponent) },
      { path: 'status', loadComponent: () => import('./features/platform-detail/tabs/status-tab.component').then(m => m.StatusTabComponent) },
      { path: '', redirectTo: 'dpps', pathMatch: 'full' }
    ]
  },
  {
    path: 'platforms/:id/dpps/:dppId',
    loadComponent: () => import('./features/dpp-editor/dpp-editor.component').then(m => m.DppEditorComponent)
  },
  {
    path: 'platforms/:id/dpps/:dppId/revisions/:version',
    loadComponent: () => import('./features/dpp-editor/dpp-editor.component').then(m => m.DppEditorComponent)
  },
  { path: '**', redirectTo: '' }
];
