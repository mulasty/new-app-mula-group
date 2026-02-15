import axios from "axios";

import { api } from "@/shared/api/client";
import { MeResponse, TokenResponse } from "@/shared/api/types";

type LoginPayload = {
  email: string;
  password: string;
};

type RegisterPayload = {
  email: string;
  password: string;
  full_name?: string;
  tenant_id?: string;
};

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const response = await api.post<TokenResponse>("/auth/login", payload);
  return response.data;
}

export async function register(payload: RegisterPayload): Promise<void> {
  if (!payload.tenant_id) {
    throw new Error("Tenant ID is required for /auth/register");
  }

  try {
    await api.post(
      "/auth/register",
      {
        email: payload.email,
        password: payload.password,
        full_name: payload.full_name,
      },
      {
        headers: {
          "X-Tenant-ID": payload.tenant_id,
        },
      }
    );
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      await api.post("/signup", {
        company_name: payload.full_name || `Tenant ${payload.email.split("@")[0]}`,
        owner_email: payload.email,
        owner_password: payload.password,
      });
      return;
    }
    throw error;
  }
}

export async function me(): Promise<MeResponse> {
  const response = await api.get<MeResponse>("/auth/me");
  return response.data;
}
