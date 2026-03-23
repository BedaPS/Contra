import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../../environments/environment';

/**
 * Prepends the API base URL to relative request paths.
 */
export const apiBaseUrlInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.url.startsWith('/api')) {
    const apiReq = req.clone({ url: `${environment.apiBaseUrl}${req.url.slice(4)}` });
    return next(apiReq);
  }
  return next(req);
};
