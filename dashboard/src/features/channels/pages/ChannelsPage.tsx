import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { getCurrentBilling } from "@/shared/api/billingApi";
import { createWebsiteChannel, listChannels, listMetaConnections } from "@/shared/api/channelsApi";
import { getConnectorOauthStartUrl, listAvailableConnectors } from "@/shared/api/connectorsApi";
import { getApiErrorMessage, isEndpointMissing } from "@/shared/api/errors";
import { listProjects } from "@/shared/api/projectsApi";
import { ConnectorAvailability } from "@/shared/api/types";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { ProjectSwitcher } from "@/shared/components/ProjectSwitcher";
import { SmartTooltip } from "@/shared/components/SmartTooltip";
import { PlanUsageBars } from "@/shared/components/PlanUsageBars";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Modal } from "@/shared/components/ui/Modal";
import { Spinner } from "@/shared/components/ui/Spinner";
import { getActiveProjectId } from "@/shared/utils/storage";

function capabilityLabels(connector: ConnectorAvailability): string[] {
  const labels: string[] = [];
  if (connector.capabilities.text) labels.push("Text");
  if (connector.capabilities.image) labels.push("Image");
  if (connector.capabilities.video) labels.push("Video");
  if (connector.capabilities.reels) labels.push("Reels");
  if (connector.capabilities.shorts) labels.push("Shorts");
  return labels;
}

export function ChannelsPage(): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const { tenantId } = useTenant();

  const [activeProjectId, setActiveProject] = useState("");
  const [channelName, setChannelName] = useState("Website");
  const [oauthFeedback, setOauthFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [connectorModalOpen, setConnectorModalOpen] = useState(false);

  useEffect(() => {
    if (!tenantId) {
      setActiveProject("");
      return;
    }
    setActiveProject(getActiveProjectId(tenantId) ?? "");
  }, [tenantId]);

  const projectsQuery = useQuery({
    queryKey: ["projects", tenantId],
    queryFn: () => listProjects(tenantId),
    enabled: Boolean(tenantId),
  });

  const channelsQuery = useQuery({
    queryKey: ["channels", tenantId, activeProjectId],
    queryFn: () => listChannels(tenantId, activeProjectId),
    enabled: Boolean(tenantId && activeProjectId),
  });
  const billingQuery = useQuery({
    queryKey: ["billingCurrent", tenantId],
    queryFn: () => getCurrentBilling(),
    enabled: Boolean(tenantId),
  });

  const connectorsQuery = useQuery({
    queryKey: ["connectors", tenantId],
    queryFn: () => listAvailableConnectors(),
    enabled: Boolean(tenantId),
  });

  const metaConnectionsQuery = useQuery({
    queryKey: ["metaConnections", tenantId],
    queryFn: () => listMetaConnections(),
    enabled: Boolean(tenantId),
  });

  const createMutation = useMutation({
    mutationFn: () => createWebsiteChannel(activeProjectId, tenantId, channelName.trim() || "Website"),
    onSuccess: (created) => {
      queryClient.setQueryData(
        ["channels", tenantId, activeProjectId],
        (current: { items?: unknown[]; source?: string } | undefined) => ({
          items: [created.item, ...(current?.items ?? [])],
          source: created.source,
          backendMissing: created.backendMissing,
        })
      );
      pushToast("Website channel connected", "success");
    },
    onError: (error) => {
      pushToast(getApiErrorMessage(error, "Failed to connect channel"), "error");
    },
  });

  const connectorMutation = useMutation({
    mutationFn: (platform: string) => getConnectorOauthStartUrl(platform, activeProjectId || undefined),
    onSuccess: (authorizationUrl) => {
      window.location.assign(authorizationUrl);
    },
    onError: (error) => {
      pushToast(getApiErrorMessage(error, "Failed to start connector OAuth"), "error");
    },
  });

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const linkedInState = params.get("linkedin");
    const metaState = params.get("meta");
    const connected = params.get("connected");
    const reason = params.get("reason");
    if (!linkedInState && !metaState && !connected) {
      return;
    }

    let successMessage = "Connector connected successfully.";
    if (connected) {
      if (connected.endsWith("_error")) {
        const platform = connected.replace("_error", "");
        setOauthFeedback({
          type: "error",
          message: reason ? `${platform} connection failed: ${reason}` : `${platform} connection failed.`,
        });
        pushToast(`${platform} connection failed`, "error");
      } else {
        successMessage = `${connected} connected successfully.`;
        setOauthFeedback({ type: "success", message: successMessage });
        pushToast(`${connected} connected`, "success");
      }
    } else if (linkedInState) {
      if (linkedInState === "connected") {
        setOauthFeedback({ type: "success", message: "LinkedIn account connected successfully." });
        pushToast("LinkedIn connected", "success");
      } else {
        setOauthFeedback({
          type: "error",
          message: reason ? `LinkedIn connection failed: ${reason}` : "LinkedIn connection failed.",
        });
        pushToast("LinkedIn connection failed", "error");
      }
    } else if (metaState) {
      if (metaState === "connected") {
        setOauthFeedback({ type: "success", message: "Facebook and Instagram connected successfully." });
        pushToast("Meta connected", "success");
      } else {
        setOauthFeedback({
          type: "error",
          message: reason ? `Meta connection failed: ${reason}` : "Meta connection failed.",
        });
        pushToast("Meta connection failed", "error");
      }
    }

    queryClient.invalidateQueries({ queryKey: ["channels", tenantId, activeProjectId] });
    queryClient.invalidateQueries({ queryKey: ["metaConnections", tenantId] });
    queryClient.invalidateQueries({ queryKey: ["connectors", tenantId] });
    navigate("/app/channels", { replace: true });
  }, [location.search, navigate, pushToast, queryClient, tenantId, activeProjectId]);

  const hasMetaConnections = useMemo(() => {
    return (
      (metaConnectionsQuery.data?.facebook_pages.length ?? 0) > 0 ||
      (metaConnectionsQuery.data?.instagram_accounts.length ?? 0) > 0
    );
  }, [metaConnectionsQuery.data]);
  const connectorLimitReached =
    (billingQuery.data?.usage.connectors_count ?? 0) >= (billingQuery.data?.plan.max_connectors ?? Number.POSITIVE_INFINITY);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Channels"
        description="Connect channels per project. Connector catalog is dynamic and capability-aware."
        actions={
          <ProjectSwitcher
            tenantId={tenantId}
            projects={projectsQuery.data?.items ?? []}
            value={activeProjectId}
            onChange={setActiveProject}
            disabled={projectsQuery.isLoading}
          />
        }
      />

      {!tenantId ? (
        <EmptyState
          title="Tenant is required"
          description="Set tenant context before connecting channels."
          actionLabel="Open onboarding"
          onAction={() => navigate("/app/onboarding?step=1")}
        />
      ) : (
        <>
          {!activeProjectId ? (
            <EmptyState
              title="Select project first"
              description="Channel connection is project-scoped."
              actionLabel="Create project"
              onAction={() => navigate("/app/projects")}
            />
          ) : null}

          <Card title="Connect channel">
            {billingQuery.data ? (
              <div className="mb-3">
                <PlanUsageBars billing={billingQuery.data} />
              </div>
            ) : null}
            <div className="mb-3">
              <SmartTooltip
                id="connector-status"
                title="Connector status"
                message="Connected means OAuth account is available. Disabled channels stay connected but do not receive publish jobs."
              />
            </div>
            <div className="grid gap-3 md:grid-cols-[1fr_auto]">
              <input
                value={channelName}
                onChange={(event) => setChannelName(event.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                placeholder="Website channel name"
              />
              <Button
                type="button"
                disabled={!activeProjectId || createMutation.isPending || connectorLimitReached}
                onClick={() => createMutation.mutate()}
              >
                {createMutation.isPending ? "Connecting..." : "Connect website channel"}
              </Button>
            </div>
            {connectorLimitReached ? (
              <div className="mt-2 text-xs text-amber-700">Connector limit reached for current plan.</div>
            ) : null}
            <div className="mt-3 border-t border-slate-200 pt-3">
              <Button
                type="button"
                className="w-full bg-slate-800 hover:bg-slate-700"
                disabled={!activeProjectId}
                onClick={() => setConnectorModalOpen(true)}
              >
                Open connector catalog
              </Button>
            </div>
          </Card>

          {oauthFeedback ? (
            <div
              className={`rounded-md border px-3 py-2 text-sm ${
                oauthFeedback.type === "success"
                  ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                  : "border-red-300 bg-red-50 text-red-700"
              }`}
            >
              {oauthFeedback.message}
            </div>
          ) : null}

          <Card title="Meta connection status">
            {metaConnectionsQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-600">
                <Spinner /> Loading Meta connections...
              </div>
            ) : metaConnectionsQuery.isError ? (
              <div className="text-sm text-rose-600">Unable to load Meta connection details.</div>
            ) : !hasMetaConnections ? (
              <div className="text-sm text-slate-600">
                No Facebook pages or Instagram business accounts connected yet.
              </div>
            ) : (
              <div className="space-y-3 text-sm text-slate-700">
                {(metaConnectionsQuery.data?.facebook_pages ?? []).map((page) => (
                  <div key={page.id} className="rounded-md border border-slate-200 p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{page.page_name}</span>
                      <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">Facebook</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500">Page ID: {page.page_id}</div>
                  </div>
                ))}
                {(metaConnectionsQuery.data?.instagram_accounts ?? []).map((account) => (
                  <div key={account.id} className="rounded-md border border-slate-200 p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">
                        {account.username ? `@${account.username}` : account.instagram_account_id}
                      </span>
                      <span className="rounded bg-fuchsia-100 px-2 py-0.5 text-xs text-fuchsia-700">Instagram</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      Account ID: {account.instagram_account_id}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {isEndpointMissing(channelsQuery.error) ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              Endpoint not available yet. Channel list cannot be loaded.
            </div>
          ) : null}

          {channelsQuery.data?.backendMissing ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              Endpoint not available yet. Showing mock channels from local storage.
            </div>
          ) : null}

          <Card title="Connected channels">
            {channelsQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-600">
                <Spinner /> Loading channels...
              </div>
            ) : (channelsQuery.data?.items.length ?? 0) === 0 ? (
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
                      <div>
                        <div className="font-semibold capitalize">{channel.name ?? channel.type}</div>
                        <div className="text-xs text-slate-500">Type: {channel.type}</div>
                      </div>
                      {channelsQuery.data?.source === "mock" ? (
                        <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">mock</span>
                      ) : null}
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      Status:{" "}
                      <span className="font-medium capitalize text-slate-700">{channel.status ?? "active"}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {channel.capabilities_json?.text ? (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">Text</span>
                      ) : null}
                      {channel.capabilities_json?.image ? (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">Image</span>
                      ) : null}
                      {channel.capabilities_json?.video ? (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">Video</span>
                      ) : null}
                      {channel.capabilities_json?.reels ? (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">Reels</span>
                      ) : null}
                      {channel.capabilities_json?.shorts ? (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">Shorts</span>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Modal
            open={connectorModalOpen}
            title="Connect platform"
            onClose={() => setConnectorModalOpen(false)}
            maxWidthClassName="max-w-3xl"
            bodyClassName="max-h-[70vh]"
          >
            {connectorsQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-600">
                <Spinner /> Loading connectors...
              </div>
            ) : connectorsQuery.isError ? (
              <div className="text-sm text-rose-600">Unable to load connector catalog.</div>
            ) : (
              <div className="space-y-2">
                {(connectorsQuery.data ?? []).map((connector) => {
                  const labels = capabilityLabels(connector);
                  const isWebsite = connector.platform === "website";
                  const canConnect = connector.available && !isWebsite;
                  return (
                    <div
                      key={connector.platform}
                      className="rounded-md border border-slate-200 p-3"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="font-medium text-slate-900">{connector.display_name}</div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {labels.length > 0 ? (
                              labels.map((label) => (
                                <span
                                  key={`${connector.platform}-${label}`}
                                  className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700"
                                >
                                  {label}
                                </span>
                              ))
                            ) : (
                              <span className="text-xs text-slate-500">No declared capabilities</span>
                            )}
                          </div>
                        </div>
                        <Button
                          type="button"
                          className="px-3 py-1 text-xs"
                          disabled={!canConnect || connectorMutation.isPending}
                          onClick={() => {
                            if (isWebsite) {
                              pushToast("Website connector is configured via the form above.", "success");
                              return;
                            }
                            connectorMutation.mutate(connector.platform);
                          }}
                        >
                          {isWebsite ? "Manual" : connector.available ? "Connect" : "Unavailable"}
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Modal>
        </>
      )}
    </div>
  );
}
