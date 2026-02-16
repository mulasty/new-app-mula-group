export const STORAGE_KEYS = {
  accessToken: "cc_access_token",
  refreshToken: "cc_refresh_token",
  tenantId: "cc_tenant_id",
  onboardingState: "cc_onboarding_state",
  onboardingStateByTenant: "cc_onboarding_state_by_tenant",
  activeProjectByTenant: "cc_active_project_by_tenant",
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

function getOnboardingStateMap(): Record<string, OnboardingStorageState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.onboardingStateByTenant);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, OnboardingStorageState>;
    return typeof parsed === "object" && parsed ? parsed : {};
  } catch {
    return {};
  }
}

export function getOnboardingState(tenantId?: string | null): OnboardingStorageState {
  if (tenantId) {
    const mapped = getOnboardingStateMap()[tenantId];
    if (mapped) {
      return mapped;
    }
  }
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

export function setOnboardingState(state: OnboardingStorageState, tenantId?: string | null): void {
  if (tenantId) {
    const map = getOnboardingStateMap();
    map[tenantId] = state;
    localStorage.setItem(STORAGE_KEYS.onboardingStateByTenant, JSON.stringify(map));
  }
  localStorage.setItem(STORAGE_KEYS.onboardingState, JSON.stringify(state));
}

type ActiveProjectMap = Record<string, string>;

function getActiveProjectMap(): ActiveProjectMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.activeProjectByTenant);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as ActiveProjectMap;
    return typeof parsed === "object" && parsed ? parsed : {};
  } catch {
    return {};
  }
}

export function getActiveProjectId(tenantId: string): string | null {
  if (!tenantId) {
    return null;
  }
  const map = getActiveProjectMap();
  return map[tenantId] ?? null;
}

export function setActiveProjectId(tenantId: string, projectId: string): void {
  if (!tenantId) {
    return;
  }
  const map = getActiveProjectMap();
  map[tenantId] = projectId;
  localStorage.setItem(STORAGE_KEYS.activeProjectByTenant, JSON.stringify(map));
}

export function clearActiveProjectId(tenantId: string): void {
  if (!tenantId) {
    return;
  }
  const map = getActiveProjectMap();
  delete map[tenantId];
  localStorage.setItem(STORAGE_KEYS.activeProjectByTenant, JSON.stringify(map));
}

export function clearSessionStorage(): void {
  localStorage.removeItem(STORAGE_KEYS.accessToken);
  localStorage.removeItem(STORAGE_KEYS.refreshToken);
}
