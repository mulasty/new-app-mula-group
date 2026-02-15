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
