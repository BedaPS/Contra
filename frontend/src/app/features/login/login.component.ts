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
      <div class="login-card">
        <h1>Login to Contra</h1>
        <p>Use your Google account to access the reconciliation dashboard.</p>

        <div *ngIf="isLoggingIn" class="spinner">Signing in...</div>

        <div #googleSignInButton></div>

        <button class="logout" *ngIf="authService.isLoggedIn" (click)="logout()">Logout</button>
      </div>
    </div>
  `,
  styles: [
    `
      .login-shell { display:flex; align-items:center; justify-content:center; min-height:100vh; background:#03030a; color:#dde1f0; }
      .login-card { width: 360px; padding: 2rem; border-radius: 14px; background: #101123; border: 1px solid #2f3150; box-shadow: 0 16px 40px rgba(0,0,0,.45); text-align:center; }
      h1 { margin-bottom: 0.5rem; }
      .spinner { margin: 0.8rem 0; color: #98a6d8; }
      .logout { margin-top: 1rem; padding: 0.6rem 1rem; border: none; border-radius: 8px; background: #d25d5d; color: white; cursor: pointer; }
    `,
  ],
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
