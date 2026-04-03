import { Injectable, NgZone } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface AuthUser {
  sub: string;
  email: string;
  email_verified: boolean;
  name: string;
  picture?: string;
  hd?: string;
  roles?: string[];
}

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (opts: any) => void;
          renderButton: (element: HTMLElement, options: any) => void;
          prompt: () => void;
          disableAutoSelect: () => void;
        };
      };
    };
  }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly userSubject = new BehaviorSubject<AuthUser | null>(null);
  user$: Observable<AuthUser | null> = this.userSubject.asObservable();
  private _gsiInitialized = false;

  constructor(private ngZone: NgZone) {
    this.tryRestoreSession();
  }

  get isLoggedIn(): boolean {
    return !!this.userSubject.value;
  }

  get idToken(): string | null {
    return localStorage.getItem('google_id_token');
  }

  get user(): AuthUser | null {
    return this.userSubject.value;
  }

  initialize(): void {
    if (this._gsiInitialized) return;

    const clientId = environment.googleClientId;
    if (!clientId || clientId === 'YOUR_GOOGLE_CLIENT_ID') {
      console.warn('Google client id is not configured in environment');
      return;
    }

    const google = window.google?.accounts?.id;
    if (!google) {
      console.warn('Google Identity Services script not available yet');
      return;
    }

    google.initialize({
      client_id: clientId,
      callback: (response: any) => this.ngZone.run(() => this.handleCredentialResponse(response)),
      auto_select: false,
    });
    this._gsiInitialized = true;
  }

  renderButton(host: HTMLElement): void {
    const google = window.google?.accounts?.id;
    if (!google) {
      return;
    }

    google.renderButton(host, {
      theme: 'outline',
      size: 'large',
      type: 'standard',
      text: 'signin_with',
      shape: 'rectangular',
    });
  }

  signOut(): void {
    localStorage.removeItem('google_id_token');
    this.userSubject.next(null);
    const google = window.google?.accounts?.id;
    if (google?.disableAutoSelect) {
      google.disableAutoSelect();
    }
  }

  hasRole(role: string): boolean {
    return this.user?.roles?.includes(role) ?? false;
  }

  private handleCredentialResponse(response: { credential?: string }): void {
    if (!response?.credential) {
      return;
    }

    const payload = this.decodeJwt(response.credential);
    if (!payload || !payload.email) {
      return;
    }

    const user: AuthUser = {
      sub: payload.sub,
      email: payload.email,
      email_verified: payload.email_verified,
      name: payload.name ?? payload.email,
      picture: payload.picture,
      hd: payload.hd,
      roles: payload.roles ?? [],
    };

    localStorage.setItem('google_id_token', response.credential);
    this.userSubject.next(user);
  }

  private decodeJwt(token: string): any {
    const parts = token.split('.');
    if (parts.length !== 3) {
      return null;
    }

    try {
      const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      const binaryStr = atob(base64);
      const bytes = Uint8Array.from(binaryStr, (c) => c.charCodeAt(0));
      const json = new TextDecoder().decode(bytes);
      return JSON.parse(json);
    } catch {
      return null;
    }
  }

  private tryRestoreSession(): void {
    const idToken = this.idToken;
    if (!idToken) {
      return;
    }
    const payload = this.decodeJwt(idToken);
    if (!payload || !payload.email) {
      localStorage.removeItem('google_id_token');
      return;
    }
    this.userSubject.next({
      sub: payload.sub,
      email: payload.email,
      email_verified: payload.email_verified,
      name: payload.name ?? payload.email,
      picture: payload.picture,
      hd: payload.hd,
      roles: payload.roles ?? [],
    });
  }
}
