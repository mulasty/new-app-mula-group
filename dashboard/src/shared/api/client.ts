import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

import { runtimeConfig } from "@/shared/config/runtime";
import {
  clearSessionStorage,
  getAccessToken,
  getRefreshToken,
  getTenantId,
  setAccessToken,
  setRefreshToken,
} from "@/shared/utils/storage";

type ClientHandlers = {
  onLogout?: () => void;
  onApiError?: (message: string) => void;
};

let handlers: ClientHandlers = {};
let refreshAttempted = false;

function shouldBypassRefresh(url?: string): boolean {
  if (!url) {
    return false;
  }

  return ["/auth/login", "/auth/register", "/signup", "/auth/refresh"].some((path) => url.includes(path));
}

function getErrorMessage(error: AxiosError): string {
  const detail =
    error.response?.data && typeof error.response.data === "object"
      ? (error.response.data as { detail?: unknown }).detail
      : undefined;
  if (typeof detail === "string" && detail.trim().length > 0) {
    return detail;
  }
  return "Request failed";
}

export function registerClientHandlers(nextHandlers: ClientHandlers): void {
  handlers = nextHandlers;
}

export const api = axios.create({
  baseURL: runtimeConfig.apiBaseUrl,
  timeout: 10000,
});

const refreshClient = axios.create({
  baseURL: runtimeConfig.apiBaseUrl,
  timeout: 10000,
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  const tenantId = getTenantId();

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  if (tenantId) {
    config.headers["X-Tenant-ID"] = tenantId;
  }

  return config;
});

api.interceptors.response.use(
  (response) => {
    refreshAttempted = false;
    return response;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
    const requestUrl = originalRequest?.url;

    if (shouldBypassRefresh(requestUrl)) {
      return Promise.reject(error);
    }

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !refreshAttempted) {
      originalRequest._retry = true;
      refreshAttempted = true;

      const refreshToken = getRefreshToken();
      const tenantId = getTenantId();

      if (refreshToken && tenantId) {
        try {
          const refreshResponse = await refreshClient.post(
            "/auth/refresh",
            { refresh_token: refreshToken },
            { headers: { "X-Tenant-ID": tenantId } }
          );

          const nextAccessToken = refreshResponse.data.access_token as string;
          const nextRefreshToken = refreshResponse.data.refresh_token as string;

          setAccessToken(nextAccessToken);
          if (nextRefreshToken) {
            setRefreshToken(nextRefreshToken);
          }

          originalRequest.headers.Authorization = `Bearer ${nextAccessToken}`;
          return api(originalRequest);
        } catch {
          clearSessionStorage();
          handlers.onLogout?.();
        }
      } else {
        clearSessionStorage();
        handlers.onLogout?.();
      }
    }

    if (error.response && error.response.status >= 400 && error.response.status !== 401) {
      // Missing endpoints are handled with explicit in-page banners.
      if (![404, 405, 501].includes(error.response.status)) {
        handlers.onApiError?.(getErrorMessage(error));
      }
    }

    return Promise.reject(error);
  }
);
