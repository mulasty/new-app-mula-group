import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { me } from "@/shared/api/authApi";
import { getCurrentBilling } from "@/shared/api/billingApi";
import { getConnectorOauthStartUrl, listAvailableConnectors } from "@/shared/api/connectorsApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { listFeatureFlags, patchFeatureFlag } from "@/shared/api/featureFlagsApi";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Spinner } from "@/shared/components/ui/Spinner";

export function SettingsPage(): JSX.Element {
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const { tenantId } = useTenant();
  const profileQuery = useQuery({
    queryKey: ["me"],
    queryFn: me,
  });
  const connectorsQuery = useQuery({
    queryKey: ["connectors", tenantId],
    queryFn: () => listAvailableConnectors(),
    enabled: Boolean(tenantId),
  });
  const flagsQuery = useQuery({
    queryKey: ["settingsFeatureFlags", tenantId],
    queryFn: () => listFeatureFlags(),
    enabled: Boolean(tenantId),
  });
  const billingQuery = useQuery({
    queryKey: ["billingCurrent", tenantId],
    queryFn: () => getCurrentBilling(),
    enabled: Boolean(tenantId),
  });

  const oauthMutation = useMutation({
    mutationFn: (platform: string) => getConnectorOauthStartUrl(platform),
    onSuccess: (authorizationUrl) => {
      window.location.assign(authorizationUrl);
    },
    onError: (error) => {
      pushToast(getApiErrorMessage(error, "Failed to start connector OAuth"), "error");
    },
  });
  const flagMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      patchFeatureFlag(id, { enabled_for_tenant: enabled }),
    onSuccess: () => {
      pushToast("Feature flag updated", "success");
      void flagsQuery.refetch();
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to update feature flag"), "error"),
  });

  const externalConnectors = useMemo(
    () => (connectorsQuery.data ?? []).filter((connector) => connector.platform !== "website"),
    [connectorsQuery.data]
  );

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
        {billingQuery.data ? (
          <div className="mt-2 text-sm text-slate-700">
            Plan: <span className="font-semibold">{billingQuery.data.plan.name}</span> | Posts used:{" "}
            {billingQuery.data.usage.posts_used_current_period} / {billingQuery.data.plan.max_posts_per_month}
          </div>
        ) : null}
      </Card>

      <Card title="Feature Flags (Beta)">
        {!tenantId ? (
          <div className="text-sm text-slate-600">Set tenant context to manage flags.</div>
        ) : flagsQuery.isLoading ? (
          <div className="text-sm text-slate-600">Loading feature flags...</div>
        ) : (
          <div className="space-y-2">
            {(flagsQuery.data ?? []).map((flag) => (
              <div key={flag.id} className="flex items-center justify-between rounded border border-slate-200 p-3">
                <div>
                  <div className="text-sm font-semibold text-slate-900">{flag.key}</div>
                  <div className="text-xs text-slate-500">{flag.description}</div>
                </div>
                <Button
                  type="button"
                  className={flag.effective_enabled ? "bg-emerald-600 hover:bg-emerald-500" : ""}
                  disabled={flagMutation.isPending}
                  onClick={() => flagMutation.mutate({ id: flag.id, enabled: !flag.enabled_for_tenant })}
                >
                  {flag.effective_enabled ? "Enabled" : "Enable"}
                </Button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="API Accounts">
        {!tenantId ? (
          <div className="space-y-3 text-sm text-slate-700">
            <p>Set tenant context first to connect API accounts.</p>
            <Button type="button" onClick={() => navigate("/app/onboarding?step=1")}>
              Open onboarding
            </Button>
          </div>
        ) : connectorsQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <Spinner /> Loading available connectors...
          </div>
        ) : connectorsQuery.isError ? (
          <div className="text-sm text-rose-600">Unable to load connector catalog.</div>
        ) : externalConnectors.length === 0 ? (
          <div className="text-sm text-slate-600">No external API connectors available.</div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              Connect social accounts at tenant level. Then assign channels in <span className="font-medium">Channels</span>.
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {externalConnectors.map((connector) => (
                <div key={connector.platform} className="rounded-md border border-slate-200 p-3">
                  <div className="mb-2 text-sm font-semibold text-slate-900">{connector.display_name}</div>
                  <Button
                    type="button"
                    className="w-full"
                    disabled={!connector.available || oauthMutation.isPending}
                    onClick={() => oauthMutation.mutate(connector.platform)}
                  >
                    {connector.available ? "Connect account" : "Unavailable"}
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
