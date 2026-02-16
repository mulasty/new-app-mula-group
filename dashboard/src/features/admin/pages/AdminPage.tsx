import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { useAuth } from "@/app/providers/AuthProvider";
import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import {
  getAdminSystemOverview,
  impersonateTenant,
  listAdminAuditLogs,
  listAdminIncidents,
  listAdminTenants,
  resolveIncident,
  setGlobalPublishBreaker,
  setMaintenanceMode,
} from "@/shared/api/adminApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { setAccessToken, setRefreshToken } from "@/shared/utils/storage";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";

export function AdminPage(): JSX.Element {
  const { user } = useAuth();
  const { setTenant } = useTenant();
  const { pushToast } = useToast();
  const [selectedTenantId, setSelectedTenantId] = useState("");

  const isAllowed = Boolean(user?.is_platform_admin);
  const tenantsQuery = useQuery({
    queryKey: ["adminTenants"],
    queryFn: listAdminTenants,
    enabled: isAllowed,
  });
  const logsQuery = useQuery({
    queryKey: ["adminAuditLogs", selectedTenantId],
    queryFn: () => listAdminAuditLogs(selectedTenantId || undefined),
    enabled: isAllowed,
  });
  const systemOverviewQuery = useQuery({
    queryKey: ["adminSystemOverview"],
    queryFn: getAdminSystemOverview,
    enabled: isAllowed,
    refetchInterval: 30000,
  });
  const incidentsQuery = useQuery({
    queryKey: ["adminIncidents"],
    queryFn: () => listAdminIncidents("open"),
    enabled: isAllowed,
    refetchInterval: 15000,
  });

  const impersonateMutation = useMutation({
    mutationFn: (tenantId: string) => impersonateTenant(tenantId),
    onSuccess: (payload) => {
      setAccessToken(payload.access_token);
      setRefreshToken(payload.refresh_token);
      setTenant(payload.tenant_id);
      window.location.assign("/app");
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to impersonate tenant"), "error"),
  });
  const resolveIncidentMutation = useMutation({
    mutationFn: (incidentId: string) => resolveIncident(incidentId),
    onSuccess: () => {
      pushToast("Incident resolved", "success");
      void incidentsQuery.refetch();
      void systemOverviewQuery.refetch();
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to resolve incident"), "error"),
  });
  const globalBreakerMutation = useMutation({
    mutationFn: (enabled: boolean) => setGlobalPublishBreaker(enabled, "manual_admin_override"),
    onSuccess: () => {
      pushToast("Global publish breaker updated", "success");
      void systemOverviewQuery.refetch();
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to update global breaker"), "error"),
  });
  const maintenanceMutation = useMutation({
    mutationFn: (enabled: boolean) => setMaintenanceMode(enabled),
    onSuccess: () => pushToast("Maintenance mode updated", "success"),
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to update maintenance mode"), "error"),
  });

  if (!isAllowed) {
    return <EmptyState title="Admin only" description="Your account is not authorized for platform admin tools." />;
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Admin Panel" description="Tenant operations, audit review, and support utilities." />

      <Card title="System Control">
        {systemOverviewQuery.data ? (
          <div className="space-y-3">
            <div className="grid gap-2 md:grid-cols-4">
              <div className="rounded border p-3">
                <div className="text-xs text-slate-500">Health score</div>
                <div className="text-2xl font-bold">{systemOverviewQuery.data.system_health_score}</div>
              </div>
              <div className="rounded border p-3">
                <div className="text-xs text-slate-500">Queue depth</div>
                <div className="text-2xl font-bold">{systemOverviewQuery.data.worker_queue_depth}</div>
              </div>
              <div className="rounded border p-3">
                <div className="text-xs text-slate-500">Total MRR</div>
                <div className="text-2xl font-bold">${systemOverviewQuery.data.revenue.total_mrr}</div>
              </div>
              <div className="rounded border p-3">
                <div className="text-xs text-slate-500">Avg churn risk</div>
                <div className="text-2xl font-bold">{(systemOverviewQuery.data.revenue.avg_churn_risk_score * 100).toFixed(0)}%</div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={() => globalBreakerMutation.mutate(true)}>
                Enable global publish breaker
              </Button>
              <Button type="button" className="bg-slate-700 hover:bg-slate-600" onClick={() => globalBreakerMutation.mutate(false)}>
                Disable global publish breaker
              </Button>
              <Button type="button" className="bg-amber-600 hover:bg-amber-500" onClick={() => maintenanceMutation.mutate(true)}>
                Enable maintenance mode
              </Button>
              <Button type="button" className="bg-amber-700 hover:bg-amber-600" onClick={() => maintenanceMutation.mutate(false)}>
                Disable maintenance mode
              </Button>
            </div>
            <div className="rounded border p-3">
              <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Top tenant risk</div>
              <div className="space-y-1">
                {(systemOverviewQuery.data.tenant_risk_ranking ?? []).slice(0, 5).map((item) => (
                  <div key={item.company_id} className="flex items-center justify-between text-sm">
                    <span className="font-mono text-xs text-slate-600">{item.company_id.slice(0, 8)}</span>
                    <span className="font-semibold text-slate-900">{item.risk_score}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-slate-600">Loading system overview...</div>
        )}
      </Card>

      <Card title="Tenants">
        {tenantsQuery.isLoading ? (
          <div className="text-sm text-slate-600">Loading tenants...</div>
        ) : (
          <div className="space-y-2">
            {(tenantsQuery.data ?? []).map((tenant) => (
              <div key={tenant.company_id} className="flex flex-wrap items-center justify-between gap-2 rounded border p-3">
                <div>
                  <div className="font-semibold text-slate-900">{tenant.name}</div>
                  <div className="text-xs text-slate-500">
                    {tenant.company_id} | {tenant.subscription_status} | posts used: {tenant.posts_used_current_period}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    className="bg-slate-700 hover:bg-slate-600"
                    onClick={() => setSelectedTenantId(tenant.company_id)}
                  >
                    View logs
                  </Button>
                  <Button
                    type="button"
                    disabled={impersonateMutation.isPending}
                    onClick={() => impersonateMutation.mutate(tenant.company_id)}
                  >
                    Impersonate
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Audit Logs">
        {logsQuery.isLoading ? (
          <div className="text-sm text-slate-600">Loading logs...</div>
        ) : (logsQuery.data?.length ?? 0) === 0 ? (
          <div className="text-sm text-slate-600">No audit logs found.</div>
        ) : (
          <div className="space-y-2">
            {(logsQuery.data ?? []).slice(0, 50).map((entry) => (
              <div key={entry.id} className="rounded border p-3">
                <div className="text-sm font-semibold text-slate-900">{entry.action}</div>
                <div className="text-xs text-slate-500">{entry.created_at}</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Active Incidents">
        {incidentsQuery.isLoading ? (
          <div className="text-sm text-slate-600">Loading incidents...</div>
        ) : (incidentsQuery.data?.length ?? 0) === 0 ? (
          <div className="text-sm text-slate-600">No active incidents.</div>
        ) : (
          <div className="space-y-2">
            {(incidentsQuery.data ?? []).map((incident) => (
              <div key={incident.id} className="rounded border p-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-slate-900">{incident.incident_type}</div>
                    <div className="text-xs text-slate-500">{incident.message}</div>
                  </div>
                  <Button
                    type="button"
                    className="bg-emerald-600 px-3 py-1 text-xs hover:bg-emerald-500"
                    disabled={resolveIncidentMutation.isPending}
                    onClick={() => resolveIncidentMutation.mutate(incident.id)}
                  >
                    Resolve
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
