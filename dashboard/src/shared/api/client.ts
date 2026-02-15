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
      handlers.onApiError?.("Request failed");
    }

    return Promise.reject(error);
  }
);
