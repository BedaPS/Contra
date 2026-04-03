const isProd = typeof window !== 'undefined' && !window.location.hostname.includes('localhost');

export const environment = {
  production: isProd,
  apiBaseUrl: isProd
    ? 'https://contra-backend.kindocean-e4017e1d.centralindia.azurecontainerapps.io/api/v1'
    : 'http://localhost:8000/api/v1',
  googleClientId: 'YOUR_GOOGLE_CLIENT_ID', // TODO: set in production with real client ID
};
