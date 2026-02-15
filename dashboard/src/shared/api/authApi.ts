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
  company_name?: string;
};

type SignupResponse = {
  company: {
    id: string;
    name: string;
    slug: string;
  };
  tokens?: {
    access_token?: string;
    refresh_token?: string;
    token_type?: string;
  };
};

type RegisterResult = {
  tenant_id: string;
};

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const response = await api.post<TokenResponse>("/auth/login", payload);
  return response.data;
}

export async function register(payload: RegisterPayload): Promise<RegisterResult> {
  // Prefer tenant-scoped register when tenant context is explicitly provided.
  try {
    if (payload.tenant_id) {
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
      return { tenant_id: payload.tenant_id };
    }
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      // Fallback handled below via /signup.
    } else {
      throw error;
    }
  }

  const signupResponse = await api.post<SignupResponse>("/signup", {
    company_name: payload.company_name || payload.full_name || `Tenant ${payload.email.split("@")[0]}`,
    owner_email: payload.email,
    owner_password: payload.password,
  });
  const tenantId = signupResponse.data?.company?.id;
  if (!tenantId) {
    throw new Error("Signup response did not include tenant id");
  }
  return { tenant_id: tenantId };
}

export async function me(): Promise<MeResponse> {
  const response = await api.get<MeResponse>("/auth/me");
  return response.data;
}
