import { Component, OnInit, ViewChild, ElementRef } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="login-shell">

      <!-- Ambient blobs -->
      <div class="blob blob-1"></div>
      <div class="blob blob-2"></div>
      <div class="blob blob-3"></div>

      <div class="login-card">

        <!-- Logo -->
        <div class="logo-wrap">
          <svg class="logo-icon" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="40" height="40" rx="10" fill="url(#grad)"/>
            <path d="M12 20 L18 26 L28 14" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
            <defs>
              <linearGradient id="grad" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
                <stop stop-color="#6366f1"/>
                <stop offset="1" stop-color="#8b5cf6"/>
              </linearGradient>
            </defs>
          </svg>
          <span class="logo-text">Contra</span>
        </div>

        <!-- Headline -->
        <h1>Welcome back</h1>
        <p class="subtitle">Sign in to access the AI-powered<br>financial reconciliation dashboard.</p>

        <!-- Divider -->
        <div class="divider">
          <span>Continue with</span>
        </div>

        <!-- Google button mount point -->
        <div class="google-btn-wrap">
          <div *ngIf="isLoggingIn" class="signing-in">
            <span class="dot-pulse"></span>
            Signing in…
          </div>
          <div #googleSignInButton></div>
        </div>

        <!-- Already logged in — logout option -->
        <button class="btn-logout" *ngIf="authService.isLoggedIn" (click)="logout()">
          Sign out
        </button>

        <!-- Footer note -->
        <p class="footer-note">
          Secure access via Google OAuth 2.0 &nbsp;·&nbsp; No password required
        </p>

      </div>
    </div>
  `,
  styles: [`
    /* ── Shell ──────────────────────────────────────────────── */
    .login-shell {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      background: #05050f;
      overflow: hidden;
      font-family: 'Inter', sans-serif;
      color: #e2e4f0;
    }

    /* ── Ambient blobs ──────────────────────────────────────── */
    .blob {
      position: absolute;
      border-radius: 50%;
      filter: blur(90px);
      opacity: 0.18;
      animation: drift 14s ease-in-out infinite alternate;
    }
    .blob-1 {
      width: 520px; height: 520px;
      background: radial-gradient(circle, #6366f1, transparent 70%);
      top: -160px; left: -160px;
      animation-duration: 16s;
    }
    .blob-2 {
      width: 400px; height: 400px;
      background: radial-gradient(circle, #8b5cf6, transparent 70%);
      bottom: -120px; right: -100px;
      animation-duration: 20s;
      animation-delay: -5s;
    }
    .blob-3 {
      width: 260px; height: 260px;
      background: radial-gradient(circle, #06b6d4, transparent 70%);
      top: 55%; left: 55%;
      opacity: 0.1;
      animation-duration: 22s;
      animation-delay: -9s;
    }
    @keyframes drift {
      from { transform: translate(0, 0) scale(1); }
      to   { transform: translate(40px, 30px) scale(1.06); }
    }

    /* ── Card ───────────────────────────────────────────────── */
    .login-card {
      position: relative;
      z-index: 1;
      width: 400px;
      padding: 2.75rem 2.5rem 2.25rem;
      border-radius: 20px;
      background: rgba(14, 14, 28, 0.82);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border: 1px solid rgba(99, 102, 241, 0.2);
      box-shadow:
        0 0 0 1px rgba(255,255,255,0.04) inset,
        0 24px 60px rgba(0, 0, 0, 0.55),
        0 0 80px rgba(99, 102, 241, 0.08);
      text-align: center;
    }

    /* ── Logo ───────────────────────────────────────────────── */
    .logo-wrap {
      display: inline-flex;
      align-items: center;
      gap: 0.6rem;
      margin-bottom: 1.75rem;
    }
    .logo-icon {
      width: 40px;
      height: 40px;
      flex-shrink: 0;
      filter: drop-shadow(0 4px 12px rgba(99, 102, 241, 0.5));
    }
    .logo-text {
      font-size: 1.45rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      background: linear-gradient(135deg, #a5b4fc 0%, #c4b5fd 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    /* ── Heading ────────────────────────────────────────────── */
    h1 {
      font-size: 1.7rem;
      font-weight: 700;
      letter-spacing: -0.025em;
      color: #f1f1f8;
      margin-bottom: 0.5rem;
    }
    .subtitle {
      font-size: 0.875rem;
      line-height: 1.6;
      color: #8b8fa8;
      margin-bottom: 0;
    }

    /* ── Divider ────────────────────────────────────────────── */
    .divider {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin: 1.75rem 0 1.25rem;
      color: #474b6a;
      font-size: 0.78rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .divider::before,
    .divider::after {
      content: '';
      flex: 1;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(99,102,241,0.25), transparent);
    }

    /* ── Google button container ────────────────────────────── */
    .google-btn-wrap {
      display: flex;
      justify-content: center;
      min-height: 44px;
      align-items: center;
    }

    /* ── Signing-in state ───────────────────────────────────── */
    .signing-in {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      color: #8b8fa8;
      font-size: 0.875rem;
    }
    .dot-pulse {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #6366f1;
      animation: pulse 1.2s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50%       { opacity: 0.4; transform: scale(0.7); }
    }

    /* ── Logout button ──────────────────────────────────────── */
    .btn-logout {
      margin-top: 1rem;
      padding: 0.55rem 1.25rem;
      border: 1px solid rgba(220, 80, 80, 0.4);
      border-radius: 8px;
      background: rgba(220, 80, 80, 0.08);
      color: #f87171;
      font-size: 0.875rem;
      cursor: pointer;
      transition: background 0.2s, border-color 0.2s;
    }
    .btn-logout:hover {
      background: rgba(220, 80, 80, 0.16);
      border-color: rgba(220, 80, 80, 0.6);
    }

    /* ── Footer note ────────────────────────────────────────── */
    .footer-note {
      margin-top: 1.75rem;
      font-size: 0.72rem;
      color: #474b6a;
      letter-spacing: 0.01em;
    }
  `],
})
export class LoginComponent implements OnInit {
  @ViewChild('googleSignInButton', { static: true }) googleButton!: ElementRef<HTMLElement>;
  isLoggingIn = false;

  constructor(public authService: AuthService, private router: Router) {}

  ngOnInit(): void {
    if (this.authService.isLoggedIn) {
      this.router.navigate(['/pipeline']);
      return;
    }

    this.authService.user$.subscribe((user) => {
      this.isLoggingIn = false;
      if (user?.email) {
        this.router.navigate(['/pipeline']);
      }
    });

    this.mountGoogleButton();
  }

  private mountGoogleButton(): void {
    const tryMount = () => {
      if (window.google?.accounts?.id) {
        this.authService.initialize();
        this.authService.renderButton(this.googleButton.nativeElement);
      } else {
        setTimeout(tryMount, 150);
      }
    };
    tryMount();
  }

  logout(): void {
    this.authService.signOut();
  }
}
