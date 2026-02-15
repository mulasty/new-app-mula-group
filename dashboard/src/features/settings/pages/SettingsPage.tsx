import { useQuery } from "@tanstack/react-query";

import { useTenant } from "@/app/providers/TenantProvider";
import { me } from "@/shared/api/authApi";
import { PageHeader } from "@/shared/components/PageHeader";
import { Card } from "@/shared/components/ui/Card";

export function SettingsPage(): JSX.Element {
  const { tenantId } = useTenant();
  const profileQuery = useQuery({
    queryKey: ["me"],
    queryFn: me,
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Profile and tenant context information." />

      <Card title="Profile">
        {profileQuery.isLoading ? <div className="text-sm text-slate-500">Loading profile...</div> : null}
        {profileQuery.data ? (
          <dl className="grid gap-2 text-sm text-slate-700">
            <div>
              <dt className="font-semibold">Email</dt>
              <dd>{profileQuery.data.email}</dd>
            </div>
            <div>
              <dt className="font-semibold">Role</dt>
              <dd>{profileQuery.data.role ?? "n/a"}</dd>
            </div>
          </dl>
        ) : null}
      </Card>

      <Card title="Tenant">
        <div className="text-sm text-slate-700">Current tenant: {tenantId || "not set"}</div>
      </Card>
    </div>
  );
}
