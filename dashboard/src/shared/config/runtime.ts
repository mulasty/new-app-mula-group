export const runtimeConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api",
  sessionInactivityMs: 12 * 60 * 60 * 1000,
  featureFlags: {
    enableMockFallback: true,
  },
};

export type RuntimeConfig = typeof runtimeConfig;
