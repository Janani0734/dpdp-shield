import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  { path: 'dashboard', title: 'Dashboard · DPDP-Shield', loadComponent: () => import('./features/dashboard/dashboard.page').then((m) => m.DashboardPage) },
  { path: 'workspace', title: 'Policy workspace · DPDP-Shield', loadComponent: () => import('./features/workspace/workspace.page').then((m) => m.WorkspacePage) },
  { path: 'chat', title: 'Ask questions · DPDP-Shield', loadComponent: () => import('./features/chat/chat.page').then((m) => m.ChatPage) },
  { path: 'report', title: 'Gap report · DPDP-Shield', loadComponent: () => import('./features/report/report.page').then((m) => m.ReportPage) },
  { path: 'audit', title: 'Audit · DPDP-Shield', loadComponent: () => import('./features/audit/audit.page').then((m) => m.AuditPage) },
  { path: '**', redirectTo: 'dashboard' },
];
