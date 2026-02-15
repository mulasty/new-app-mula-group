function envBool(value: string | undefined, fallback: boolean): boolean {
  if (value == null) {
    return fallback;
  }
  return value.toLowerCase() === "true";
}

export const runtimeConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api",
  sessionInactivityMs: 12 * 60 * 60 * 1000,
  featureFlags: {
    enableMockFallback: envBool(import.meta.env.VITE_ENABLE_MOCK_FALLBACK, false),
  },
};

export type RuntimeConfig = typeof runtimeConfig;
