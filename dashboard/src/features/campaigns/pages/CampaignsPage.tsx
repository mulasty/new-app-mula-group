import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { activateCampaign, createCampaign, listCampaigns, pauseCampaign } from "@/shared/api/automationApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { listProjects } from "@/shared/api/projectsApi";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { ProjectSwitcher } from "@/shared/components/ProjectSwitcher";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Input } from "@/shared/components/ui/Input";

export function CampaignsPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { tenantId } = useTenant();

  const [activeProjectId, setActiveProjectId] = useState("");
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("Europe/Warsaw");
  const [language, setLanguage] = useState("pl");
  const [voice, setVoice] = useState("professional");

  const projectsQuery = useQuery({
    queryKey: ["projects", tenantId],
    queryFn: () => listProjects(tenantId),
    enabled: Boolean(tenantId),
  });

  const campaignsQuery = useQuery({
    queryKey: ["campaigns", tenantId, activeProjectId],
    queryFn: () => listCampaigns(activeProjectId),
    enabled: Boolean(tenantId && activeProjectId),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createCampaign({
        project_id: activeProjectId,
        name: name.trim(),
        timezone,
        language,
        brand_profile_json: { voice },
      }),
    onSuccess: () => {
      pushToast("Campaign created", "success");
      setName("");
      queryClient.invalidateQueries({ queryKey: ["campaigns", tenantId, activeProjectId] });
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to create campaign"), "error"),
  });

  const statusMutation = useMutation({
    mutationFn: ({ campaignId, nextStatus }: { campaignId: string; nextStatus: "active" | "paused" }) =>
      nextStatus === "active" ? activateCampaign(campaignId) : pauseCampaign(campaignId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns", tenantId, activeProjectId] });
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to update campaign status"), "error"),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Campaigns"
        description="Define campaign goals, language, timezone and brand profile."
        actions={
          <ProjectSwitcher
            tenantId={tenantId}
            projects={projectsQuery.data?.items ?? []}
            value={activeProjectId}
            onChange={setActiveProjectId}
            disabled={projectsQuery.isLoading}
          />
        }
      />

      {!tenantId ? (
        <EmptyState
          title="Tenant required"
          description="Set tenant context before managing campaigns."
          actionLabel="Open onboarding"
          onAction={() => navigate("/app/onboarding?step=1")}
        />
      ) : !activeProjectId ? (
        <EmptyState
          title="Select project"
          description="Campaigns are project-scoped."
          actionLabel="Create project"
          onAction={() => navigate("/app/projects")}
        />
      ) : (
        <>
          <Card title="Create campaign">
            <div className="grid gap-2 md:grid-cols-2">
              <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Campaign name" />
              <Input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Timezone" />
              <Input value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="Language" />
              <Input value={voice} onChange={(event) => setVoice(event.target.value)} placeholder="Brand voice" />
            </div>
            <div className="mt-3">
              <Button type="button" disabled={!name.trim() || createMutation.isPending} onClick={() => createMutation.mutate()}>
                {createMutation.isPending ? "Creating..." : "Create campaign"}
              </Button>
            </div>
          </Card>

          <Card title="Campaign list">
            {(campaignsQuery.data?.length ?? 0) === 0 ? (
              <EmptyState
                title="No campaigns"
                description="Create your first campaign to start automation."
              />
            ) : (
              <div className="space-y-2">
                {(campaignsQuery.data ?? []).map((campaign) => (
                  <div key={campaign.id} className="flex items-center justify-between rounded-md border border-slate-200 p-3">
                    <div>
                      <div className="font-semibold text-slate-900">{campaign.name}</div>
                      <div className="text-xs text-slate-500">
                        {campaign.language.toUpperCase()} • {campaign.timezone} • {campaign.status}
                      </div>
                    </div>
                    <Button
                      type="button"
                      className="px-3 py-1 text-xs"
                      disabled={statusMutation.isPending}
                      onClick={() =>
                        statusMutation.mutate({
                          campaignId: campaign.id,
                          nextStatus: campaign.status === "active" ? "paused" : "active",
                        })
                      }
                    >
                      {campaign.status === "active" ? "Pause" : "Activate"}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
