import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { createChannel, listChannels } from "@/shared/api/channelsApi";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";

export function ChannelsPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = useTenant();

  const [type, setType] = useState<"website" | "facebook" | "instagram" | "youtube">("website");
  const [credentialsJson, setCredentialsJson] = useState("{}");

  const channelsQuery = useQuery({
    queryKey: ["channels", tenantId],
    queryFn: () => listChannels(tenantId),
    enabled: Boolean(tenantId),
  });

  const createMutation = useMutation({
    mutationFn: () => createChannel({ type, credentials_json: credentialsJson }, tenantId),
    onSuccess: (created) => {
      queryClient.setQueryData(["channels", tenantId], (current: { items?: unknown[]; source?: string } | undefined) => ({
        items: [created.item, ...(current?.items ?? [])],
        source: created.source,
        backendMissing: created.backendMissing,
      }));
      setCredentialsJson("{}");
    },
  });

  const jsonError = useMemo(() => {
    try {
      JSON.parse(credentialsJson);
      return null;
    } catch {
      return "credentials_json must be valid JSON";
    }
  }, [credentialsJson]);

  return (
    <div className="space-y-6">
      <PageHeader title="Channels" description="Connect social and website channels for distribution." />

      {!tenantId ? (
        <EmptyState
          title="Tenant is required"
          description="Set tenant context before connecting channels."
          actionLabel="Open onboarding"
          onAction={() => navigate("/app/onboarding?step=1")}
        />
      ) : (
        <>
          <Card title="Connect channel">
            <div className="grid gap-3 md:grid-cols-3">
              <select
                value={type}
                onChange={(event) => setType(event.target.value as typeof type)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="website">Website</option>
                <option value="facebook">Facebook</option>
                <option value="instagram">Instagram</option>
                <option value="youtube">YouTube</option>
              </select>
              <textarea
                value={credentialsJson}
                onChange={(event) => setCredentialsJson(event.target.value)}
                className="min-h-[44px] rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
              <Button type="button" disabled={Boolean(jsonError)} onClick={() => createMutation.mutate()}>
                Connect
              </Button>
            </div>
            {jsonError ? <div className="mt-2 text-xs text-red-600">{jsonError}</div> : null}
          </Card>

          {channelsQuery.data?.backendMissing ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              Backend endpoint missing. Showing mock channels from local storage.
            </div>
          ) : null}

          <Card title="Connected channels">
            {(channelsQuery.data?.items.length ?? 0) === 0 ? (
              <EmptyState
                title="No channels connected"
                description="Connect your first channel to schedule and publish posts."
                actionLabel="Open onboarding"
                onAction={() => navigate("/app/onboarding?step=3")}
              />
            ) : (
              <ul className="space-y-2 text-sm text-slate-700">
                {(channelsQuery.data?.items ?? []).map((channel) => (
                  <li key={channel.id} className="rounded-md border border-slate-200 p-3">
                    <div className="flex items-center justify-between">
                      <div className="font-semibold capitalize">{channel.type}</div>
                      {channelsQuery.data?.source === "mock" ? (
                        <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">mock</span>
                      ) : null}
                    </div>
                    <pre className="mt-2 overflow-auto rounded bg-slate-100 p-2 text-xs">{channel.credentials_json}</pre>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
