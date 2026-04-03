import { Routes } from '@angular/router';
import { authGuard } from './core/services/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/login/login.component').then(m => m.LoginComponent),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./shared/shell/shell.component').then(m => m.ShellComponent),
    children: [
      { path: '', redirectTo: 'pipeline', pathMatch: 'full' },
      { path: 'pipeline', loadComponent: () => import('./features/pipeline-monitor/pipeline-monitor.component').then(m => m.PipelineMonitorComponent) },
      { path: 'activity', loadComponent: () => import('./features/agent-activity/agent-activity.component').then(m => m.AgentActivityComponent) },
      { path: 'review', loadComponent: () => import('./features/document-review/document-review.component').then(m => m.DocumentReviewComponent) },
      { path: 'audit', loadComponent: () => import('./features/audit-trail/audit-trail.component').then(m => m.AuditTrailComponent) },
      { path: 'settings', loadComponent: () => import('./features/settings/settings.component').then(m => m.SettingsComponent) },
      { path: 'runs', loadComponent: () => import('./features/runs/runs.component').then(m => m.RunsComponent) },
      { path: 'results', loadComponent: () => import('./features/results/results.component').then(m => m.ResultsComponent) },
    ],
  },
];
