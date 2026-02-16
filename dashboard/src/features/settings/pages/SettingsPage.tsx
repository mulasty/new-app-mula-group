import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { me } from "@/shared/api/authApi";
import {
  cancelSubscription,
  createCheckoutSession,
  downgradeSubscription,
  getBillingHistory,
  getCurrentBilling,
  reactivateSubscription,
  upgradeSubscription,
} from "@/shared/api/billingApi";
import { getConnectorOauthStartUrl, listAvailableConnectors } from "@/shared/api/connectorsApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { listFeatureFlags, patchFeatureFlag } from "@/shared/api/featureFlagsApi";
import { PageHeader } from "@/shared/components/PageHeader";
import { PlanUsageBars } from "@/shared/components/PlanUsageBars";
import { SmartTooltip } from "@/shared/components/SmartTooltip";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Spinner } from "@/shared/components/ui/Spinner";

export function SettingsPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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
  const billingHistoryQuery = useQuery({
    queryKey: ["billingHistory", tenantId],
    queryFn: () => getBillingHistory(30),
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
  const upgradeMutation = useMutation({
    mutationFn: () => upgradeSubscription("Pro"),
    onSuccess: async () => {
      pushToast("Subscription upgraded", "success");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["billingCurrent", tenantId] }),
        queryClient.invalidateQueries({ queryKey: ["billingHistory", tenantId] }),
      ]);
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to upgrade subscription"), "error"),
  });
  const downgradeMutation = useMutation({
    mutationFn: () => downgradeSubscription("Starter"),
    onSuccess: async () => {
      pushToast("Subscription downgraded", "success");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["billingCurrent", tenantId] }),
        queryClient.invalidateQueries({ queryKey: ["billingHistory", tenantId] }),
      ]);
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to downgrade subscription"), "error"),
  });
  const cancelMutation = useMutation({
    mutationFn: (immediate: boolean) => cancelSubscription(immediate),
    onSuccess: async () => {
      pushToast("Cancellation requested", "success");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["billingCurrent", tenantId] }),
        queryClient.invalidateQueries({ queryKey: ["billingHistory", tenantId] }),
      ]);
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to cancel subscription"), "error"),
  });
  const reactivateMutation = useMutation({
    mutationFn: () => reactivateSubscription(),
    onSuccess: async () => {
      pushToast("Subscription reactivated", "success");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["billingCurrent", tenantId] }),
        queryClient.invalidateQueries({ queryKey: ["billingHistory", tenantId] }),
      ]);
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to reactivate subscription"), "error"),
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
        <div className="mb-2">
          <SmartTooltip
            id="plan-limits"
            title="Plan limits"
            message="Usage bars help prevent blocked actions. Above 80% you should consider plan upgrade to avoid interruptions."
          />
        </div>
        <div className="text-sm text-slate-700">Current tenant: {tenantId || "not set"}</div>
        {billingQuery.data ? (
          <div className="mt-3 space-y-3">
            <div className="text-sm text-slate-700">
              Plan: <span className="font-semibold">{billingQuery.data.plan.name}</span> | Status:{" "}
              <span className="font-semibold">{billingQuery.data.subscription.status}</span>
            </div>
            {billingQuery.data.lifecycle?.in_grace_period ? (
              <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                Grace period active. Days left: {billingQuery.data.lifecycle.days_left_in_period}
              </div>
            ) : null}
            {billingQuery.data.lifecycle?.expired ? (
              <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700">
                Plan expired. Reactivate or upgrade to restore full publishing.
              </div>
            ) : null}
            <PlanUsageBars billing={billingQuery.data} />
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={() => upgradeMutation.mutate()} disabled={upgradeMutation.isPending}>
                {upgradeMutation.isPending ? "Upgrading..." : "Upgrade"}
              </Button>
              <Button
                type="button"
                className="bg-slate-700 hover:bg-slate-600"
                onClick={() => downgradeMutation.mutate()}
                disabled={downgradeMutation.isPending}
              >
                {downgradeMutation.isPending ? "Downgrading..." : "Downgrade"}
              </Button>
              <Button
                type="button"
                className="bg-rose-600 hover:bg-rose-500"
                onClick={() => cancelMutation.mutate(false)}
                disabled={cancelMutation.isPending}
              >
                {cancelMutation.isPending ? "Cancelling..." : "Cancel subscription"}
              </Button>
              <Button
                type="button"
                className="bg-emerald-700 hover:bg-emerald-600"
                onClick={() => reactivateMutation.mutate()}
                disabled={reactivateMutation.isPending}
              >
                {reactivateMutation.isPending ? "Reactivating..." : "Reactivate"}
              </Button>
              <Button
                type="button"
                className="bg-slate-800 hover:bg-slate-700"
                onClick={async () => {
                  const session = await createCheckoutSession("Pro");
                  if (session.checkout_url) {
                    window.location.assign(session.checkout_url);
                  }
                }}
              >
                Open checkout
              </Button>
            </div>
          </div>
        ) : null}
      </Card>

      <Card title="Billing history">
        {billingHistoryQuery.isLoading ? (
          <div className="text-sm text-slate-600">Loading billing history...</div>
        ) : (billingHistoryQuery.data?.length ?? 0) === 0 ? (
          <div className="text-sm text-slate-600">No billing events recorded yet.</div>
        ) : (
          <div className="space-y-2">
            {(billingHistoryQuery.data ?? []).map((item) => (
              <div key={item.id} className="rounded border border-slate-200 px-3 py-2 text-xs text-slate-700">
                <div className="font-semibold text-slate-900">{item.event_type}</div>
                <div>{item.message}</div>
                <div className="text-slate-500">{new Date(item.created_at).toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
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
