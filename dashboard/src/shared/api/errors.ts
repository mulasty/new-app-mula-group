import axios from "axios";

export function isEndpointMissing(error: unknown): boolean {
  if (!axios.isAxiosError(error)) {
    return false;
  }

  return error.response?.status === 404 || error.response?.status === 405 || error.response?.status === 501;
}

export function isUnauthorized(error: unknown): boolean {
  if (!axios.isAxiosError(error)) {
    return false;
  }

  return error.response?.status === 401;
}

export function getApiErrorMessage(error: unknown, fallback = "Request failed"): string {
  if (!axios.isAxiosError(error)) {
    return fallback;
  }

  const detail = error.response?.data && typeof error.response.data === "object"
    ? (error.response.data as { detail?: unknown }).detail
    : undefined;

  if (typeof detail === "string" && detail.trim().length > 0) {
    return detail;
  }

  return fallback;
}
