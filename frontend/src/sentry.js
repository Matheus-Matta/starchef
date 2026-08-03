import * as Sentry from "@sentry/vue";

/**
 * Sentry só é inicializado se VITE_SENTRY_DSN estiver definido — sem DSN,
 * zero overhead (mesmo critério usado no backend, ver config/settings/production.py).
 */
export function initSentry(app, router) {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return;

  Sentry.init({
    app,
    dsn,
    integrations: [Sentry.browserTracingIntegration({ router })],
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || (import.meta.env.PROD ? "production" : "development"),
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
    sendDefaultPii: false,
  });
}

export { Sentry };
