import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [RouterOutlet],
  template: `
    <h1>Contra — Reconciliation Dashboard</h1>
    <p>Pipeline status and audit trail will be rendered here.</p>
    <router-outlet />
  `,
})
export class DashboardComponent {}
