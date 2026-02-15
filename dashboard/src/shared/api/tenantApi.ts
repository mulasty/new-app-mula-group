import { api } from "@/shared/api/client";
import { TenantContextResponse } from "@/shared/api/types";

export async function getTenantContext(): Promise<TenantContextResponse> {
  const response = await api.get<TenantContextResponse>("/tenant/context");
  return response.data;
}
