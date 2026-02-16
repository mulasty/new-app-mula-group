import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { useAuth } from "@/app/providers/AuthProvider";
import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { impersonateTenant, listAdminAuditLogs, listAdminTenants } from "@/shared/api/adminApi";
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

  if (!isAllowed) {
    return <EmptyState title="Admin only" description="Your account is not authorized for platform admin tools." />;
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Admin Panel" description="Tenant operations, audit review, and support utilities." />

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
    </div>
  );
}
