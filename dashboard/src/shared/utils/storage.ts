export const STORAGE_KEYS = {
  accessToken: "cc_access_token",
  refreshToken: "cc_refresh_token",
  tenantId: "cc_tenant_id",
  onboardingState: "cc_onboarding_state",
};

export type OnboardingStorageState = {
  skipped: boolean;
  completed: boolean;
};

export function getAccessToken(): string | null {
  return localStorage.getItem(STORAGE_KEYS.accessToken);
}

export function setAccessToken(token: string): void {
  localStorage.setItem(STORAGE_KEYS.accessToken, token);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(STORAGE_KEYS.refreshToken);
}

export function setRefreshToken(token: string): void {
  localStorage.setItem(STORAGE_KEYS.refreshToken, token);
}

export function getTenantId(): string | null {
  return localStorage.getItem(STORAGE_KEYS.tenantId);
}

export function setTenantId(tenantId: string): void {
  localStorage.setItem(STORAGE_KEYS.tenantId, tenantId);
}

export function getOnboardingState(): OnboardingStorageState {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.onboardingState);
    if (!raw) {
      return { skipped: false, completed: false };
    }
    return JSON.parse(raw) as OnboardingStorageState;
  } catch {
    return { skipped: false, completed: false };
  }
}

export function setOnboardingState(state: OnboardingStorageState): void {
  localStorage.setItem(STORAGE_KEYS.onboardingState, JSON.stringify(state));
}

export function clearSessionStorage(): void {
  localStorage.removeItem(STORAGE_KEYS.accessToken);
  localStorage.removeItem(STORAGE_KEYS.refreshToken);
}
