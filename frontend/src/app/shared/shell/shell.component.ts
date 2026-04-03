import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Observable } from 'rxjs';
import { AuthService, AuthUser } from '../../core/services/auth.service';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="shell">
      <header class="topbar">
        <div class="brand">Contra Reconciliation</div>
        <div class="user-controls" *ngIf="(user$ | async) as user; else noUser">
          <img *ngIf="user.picture" [src]="user.picture" alt="user" class="avatar" />
          <span>{{ user.name }}</span>
          <button class="btn-logout" (click)="signOut()">Logout</button>
        </div>
        <ng-template #noUser>
          <span><a routerLink="/login">Sign in with Google</a></span>
        </ng-template>
      </header>
      <nav class="sidebar">
        <div class="logo">
          <span class="logo-icon">◈</span>
          <span class="logo-text">Contra</span>
        </div>
        <ul class="nav-list">
          <li>
            <a routerLink="/pipeline" routerLinkActive="active">
              <span class="nav-icon">▶</span>
              Pipeline Monitor
            </a>
          </li>
          <li>
            <a routerLink="/activity" routerLinkActive="active">
              <span class="nav-icon">◉</span>
              Agent Activity
            </a>
          </li>
          <li>
            <a routerLink="/review" routerLinkActive="active">
              <span class="nav-icon">⚑</span>
              Document Review
            </a>
          </li>
          <li>
            <a routerLink="/audit" routerLinkActive="active">
              <span class="nav-icon">☰</span>
              Audit Trail
            </a>
          </li>
          <li>
            <a routerLink="/runs" routerLinkActive="active">
              <span class="nav-icon">⊞</span>
              Run History
            </a>
          </li>
          <li>
            <a routerLink="/results" routerLinkActive="active">
              <span class="nav-icon">⊟</span>
              Results
            </a>
          </li>
          <li>
            <a routerLink="/settings" routerLinkActive="active">
              <span class="nav-icon">⚙</span>
              Settings
            </a>
          </li>
        </ul>
        <div class="sidebar-footer">
          <span class="version">v0.1.0 — AG-UI Protocol</span>
        </div>
      </nav>
      <main class="content">
        <router-outlet />
      </main>
    </div>
  `,
  styles: [`
    .shell {
      display: flex;
      height: 100vh;
      background: #0a0a0f;
      color: #e0e0e6;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    .sidebar {
      width: 240px;
      min-width: 240px;
      background: #111118;
      border-right: 1px solid #1e1e2e;
      display: flex;
      flex-direction: column;
      padding: 1.25rem 0;
    }

    .logo {
      display: flex;
      align-items: center;
      gap: 0.625rem;
      padding: 0 1.25rem 1.25rem;
      border-bottom: 1px solid #1e1e2e;
      margin-bottom: 1rem;
    }

    .logo-icon {
      font-size: 1.5rem;
      color: #6c5ce7;
    }

    .logo-text {
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      background: linear-gradient(135deg, #6c5ce7, #a29bfe);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .nav-list {
      list-style: none;
      margin: 0;
      padding: 0;
      flex: 1;
    }

    .nav-list li a {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.75rem 1.25rem;
      color: #8888a0;
      text-decoration: none;
      font-size: 0.875rem;
      font-weight: 500;
      transition: all 0.15s ease;
      border-left: 3px solid transparent;
    }

    .nav-list li a:hover {
      color: #c0c0d0;
      background: #1a1a28;
    }

    .nav-list li a.active {
      color: #a29bfe;
      background: #1a1a28;
      border-left-color: #6c5ce7;
    }

    .nav-icon {
      font-size: 1rem;
      width: 1.25rem;
      text-align: center;
    }

    .sidebar-footer {
      padding: 1rem 1.25rem;
      border-top: 1px solid #1e1e2e;
    }

    .version {
      font-size: 0.7rem;
      color: #555570;
    }

    .topbar {
      position: fixed;
      z-index: 10;
      left: 240px;
      right: 0;
      top: 0;
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 1.5rem;
      background: #07070f;
      border-bottom: 1px solid #1e1e2e;
      color: #e0e0e6;
    }

    .brand { font-weight: 700; }

    .user-controls { display: flex; align-items: center; gap: 0.65rem; }

    .avatar { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; }

    .btn-logout {
      background: #d25d5d;
      color: white;
      border: none;
      border-radius: 8px;
      padding: 0.35rem 0.8rem;
      cursor: pointer;
    }

    .content {
      flex: 1;
      overflow-y: auto;
      padding: 6rem 2rem 2rem;
    }
  `],
})
export class ShellComponent {
  user$: Observable<AuthUser | null>;

  constructor(private authService: AuthService) {
    this.user$ = this.authService.user$;
  }

  signOut() {
    this.authService.signOut();
  }
}
