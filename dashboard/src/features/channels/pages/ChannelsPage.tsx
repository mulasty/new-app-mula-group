import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { createWebsiteChannel, listChannels } from "@/shared/api/channelsApi";
import { getApiErrorMessage, isEndpointMissing } from "@/shared/api/errors";
import { listProjects } from "@/shared/api/projectsApi";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { ProjectSwitcher } from "@/shared/components/ProjectSwitcher";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Spinner } from "@/shared/components/ui/Spinner";
import { getActiveProjectId } from "@/shared/utils/storage";

export function ChannelsPage(): JSX.Element {
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const { tenantId } = useTenant();

  const [activeProjectId, setActiveProject] = useState("");
  const [channelName, setChannelName] = useState("Website");

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

  const createMutation = useMutation({
    mutationFn: () => createWebsiteChannel(activeProjectId, tenantId, channelName.trim() || "Website"),
    onSuccess: (created) => {
      queryClient.setQueryData(["channels", tenantId, activeProjectId], (current: { items?: unknown[]; source?: string } | undefined) => ({
        items: [created.item, ...(current?.items ?? [])],
        source: created.source,
        backendMissing: created.backendMissing,
      }));
      pushToast("Website channel connected", "success");
    },
    onError: (error) => {
      pushToast(getApiErrorMessage(error, "Failed to connect channel"), "error");
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Channels"
        description="Connect website channels per project for publishing."
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
            <div className="grid gap-3 md:grid-cols-[1fr_auto]">
              <input
                value={channelName}
                onChange={(event) => setChannelName(event.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                placeholder="Channel name"
              />
              <Button
                type="button"
                disabled={!activeProjectId || createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                {createMutation.isPending ? "Connecting..." : "Connect website channel"}
              </Button>
            </div>
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
                      Status: <span className="font-medium capitalize text-slate-700">{channel.status ?? "active"}</span>
                    </div>
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
