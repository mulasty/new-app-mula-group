import { api } from "@/shared/api/client";
import { AdminAuditLogItem, AdminTenantItem } from "@/shared/api/types";

export async function listAdminTenants(): Promise<AdminTenantItem[]> {
  const response = await api.get<{ items: AdminTenantItem[] }>("/admin/tenants");
  return response.data.items ?? [];
}

export async function listAdminAuditLogs(companyId?: string): Promise<AdminAuditLogItem[]> {
  const response = await api.get<{ items: AdminAuditLogItem[] }>("/admin/audit-logs", {
    params: companyId ? { company_id: companyId } : undefined,
  });
  return response.data.items ?? [];
}

export async function impersonateTenant(tenantId: string): Promise<{ access_token: string; refresh_token: string; tenant_id: string }> {
  const response = await api.post<{ access_token: string; refresh_token: string; tenant_id: string }>(
    `/admin/tenants/${tenantId}/impersonate`
  );
  return response.data;
}
