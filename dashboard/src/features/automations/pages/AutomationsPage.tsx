import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { createRule, listRunEvents, listRuns, listRules, runRuleNow } from "@/shared/api/automationApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { listProjects } from "@/shared/api/projectsApi";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { ProjectSwitcher } from "@/shared/components/ProjectSwitcher";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Input } from "@/shared/components/ui/Input";

export function AutomationsPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { tenantId } = useTenant();

  const [activeProjectId, setActiveProjectId] = useState("");
  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState<"interval" | "cron" | "event">("interval");
  const [actionType, setActionType] = useState<"generate_post" | "schedule_post" | "publish_now" | "sync_metrics">(
    "generate_post"
  );
  const [intervalSeconds, setIntervalSeconds] = useState("300");
  const [selectedRunId, setSelectedRunId] = useState<string>("");

  const projectsQuery = useQuery({
    queryKey: ["projects", tenantId],
    queryFn: () => listProjects(tenantId),
    enabled: Boolean(tenantId),
  });

  const rulesQuery = useQuery({
    queryKey: ["automationRules", tenantId, activeProjectId],
    queryFn: () => listRules(activeProjectId),
    enabled: Boolean(tenantId && activeProjectId),
  });

  const runsQuery = useQuery({
    queryKey: ["automationRuns", tenantId, activeProjectId],
    queryFn: () => listRuns(activeProjectId),
    enabled: Boolean(tenantId && activeProjectId),
    refetchInterval: (query) => {
      const items = (query.state.data as Array<{ status: string }> | undefined) ?? [];
      return items.some((item) => item.status === "queued" || item.status === "running") ? 15000 : 30000;
    },
  });

  const eventsQuery = useQuery({
    queryKey: ["automationRunEvents", tenantId, selectedRunId],
    queryFn: () => listRunEvents(selectedRunId),
    enabled: Boolean(tenantId && selectedRunId),
    refetchInterval: 15000,
  });

  const createRuleMutation = useMutation({
    mutationFn: () =>
      createRule({
        project_id: activeProjectId,
        name: name.trim(),
        trigger_type: triggerType,
        trigger_config_json:
          triggerType === "interval" ? { interval_seconds: Number(intervalSeconds) || 300 } : { cron: "*/15 * * * *" },
        action_type: actionType,
        action_config_json: { variables: { topic: "product update", offer: "demo" } },
        guardrails_json: { approval_required: true, max_posts_per_day_project: 3 },
      }),
    onSuccess: () => {
      pushToast("Automation rule created", "success");
      setName("");
      queryClient.invalidateQueries({ queryKey: ["automationRules", tenantId, activeProjectId] });
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to create rule"), "error"),
  });

  const runNowMutation = useMutation({
    mutationFn: (ruleId: string) => runRuleNow(ruleId),
    onSuccess: () => {
      pushToast("Run queued", "success");
      queryClient.invalidateQueries({ queryKey: ["automationRuns", tenantId, activeProjectId] });
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to enqueue run"), "error"),
  });

  const latestRuns = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Automations"
        description="Build rules with triggers, actions and guardrails. Monitor run execution."
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
          description="Set tenant context first."
          actionLabel="Open onboarding"
          onAction={() => navigate("/app/onboarding?step=1")}
        />
      ) : !activeProjectId ? (
        <EmptyState
          title="Select project"
          description="Automations are project-scoped."
          actionLabel="Create project"
          onAction={() => navigate("/app/projects")}
        />
      ) : (
        <>
          <Card title="Rule builder">
            <div className="grid gap-2 md:grid-cols-2">
              <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Rule name" />
              <select
                value={triggerType}
                onChange={(event) => setTriggerType(event.target.value as typeof triggerType)}
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                <option value="interval">Interval</option>
                <option value="cron">Cron</option>
                <option value="event">Event</option>
              </select>
              <select
                value={actionType}
                onChange={(event) => setActionType(event.target.value as typeof actionType)}
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                <option value="generate_post">Generate post</option>
                <option value="schedule_post">Schedule post</option>
                <option value="publish_now">Publish now</option>
                <option value="sync_metrics">Sync metrics</option>
              </select>
              <Input
                value={intervalSeconds}
                onChange={(event) => setIntervalSeconds(event.target.value)}
                placeholder="Interval seconds"
              />
            </div>
            <div className="mt-3">
              <Button
                type="button"
                disabled={!name.trim() || createRuleMutation.isPending}
                onClick={() => createRuleMutation.mutate()}
              >
                {createRuleMutation.isPending ? "Creating..." : "Create rule"}
              </Button>
            </div>
          </Card>

          <Card title="Rules">
            {(rulesQuery.data?.length ?? 0) === 0 ? (
              <EmptyState title="No rules" description="Create first automation rule." />
            ) : (
              <div className="space-y-2">
                {(rulesQuery.data ?? []).map((rule) => (
                  <div key={rule.id} className="flex items-center justify-between rounded-md border border-slate-200 p-3">
                    <div>
                      <div className="font-medium text-slate-900">{rule.name}</div>
                      <div className="text-xs text-slate-500">
                        {`${rule.trigger_type} -> ${rule.action_type} | ${rule.is_enabled ? "enabled" : "disabled"}`}
                      </div>
                    </div>
                    <Button type="button" className="px-3 py-1 text-xs" onClick={() => runNowMutation.mutate(rule.id)}>
                      Run now
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Runs">
              {latestRuns.length === 0 ? (
                <EmptyState title="No runs" description="Run a rule to see execution tracking." />
              ) : (
                <div className="space-y-2">
                  {latestRuns.map((run) => (
                    <button
                      key={run.id}
                      type="button"
                      onClick={() => setSelectedRunId(run.id)}
                      className={`w-full rounded-md border px-3 py-2 text-left text-sm ${
                        selectedRunId === run.id ? "border-brand-700 bg-brand-50" : "border-slate-200"
                      }`}
                    >
                      <div className="font-medium text-slate-900">{run.status}</div>
                      <div className="text-xs text-slate-500">{new Date(run.created_at).toLocaleString()}</div>
                    </button>
                  ))}
                </div>
              )}
            </Card>

            <Card title="Run events">
              {!selectedRunId ? (
                <EmptyState title="Select run" description="Choose a run to inspect event timeline." />
              ) : (eventsQuery.data?.length ?? 0) === 0 ? (
                <EmptyState title="No events yet" description="Events appear while runtime executes steps." />
              ) : (
                <div className="space-y-2">
                  {(eventsQuery.data ?? []).map((event) => (
                    <div key={event.id} className="rounded-md border border-slate-200 p-3 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-slate-900">{event.event_type}</span>
                        <span className={event.status === "ok" ? "text-emerald-600" : "text-rose-600"}>{event.status}</span>
                      </div>
                      <div className="mt-1 text-xs text-slate-500">{new Date(event.created_at).toLocaleString()}</div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
