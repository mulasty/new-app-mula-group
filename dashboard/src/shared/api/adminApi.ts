import { api } from "@/shared/api/client";
import { AdminAuditLogItem, AdminSystemOverview, AdminTenantItem, PlatformIncidentItem } from "@/shared/api/types";

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

export async function getAdminSystemOverview(): Promise<AdminSystemOverview> {
  const response = await api.get<AdminSystemOverview>("/admin/system/overview");
  return response.data;
}

export async function listAdminIncidents(statusFilter = "open"): Promise<PlatformIncidentItem[]> {
  const response = await api.get<{ items: PlatformIncidentItem[] }>("/admin/incidents", {
    params: { status: statusFilter },
  });
  return response.data.items ?? [];
}

export async function resolveIncident(incidentId: string): Promise<void> {
  await api.post(`/admin/incidents/${incidentId}/resolve`);
}

export async function setGlobalPublishBreaker(enabled: boolean, reason: string): Promise<void> {
  await api.post("/admin/system/global-publish-breaker", { enabled, reason });
}

export async function setMaintenanceMode(enabled: boolean): Promise<void> {
  await api.post("/admin/system/maintenance-mode", { enabled });
}
