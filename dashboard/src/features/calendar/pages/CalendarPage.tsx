import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { getCalendar } from "@/shared/api/automationApi";
import { listProjects } from "@/shared/api/projectsApi";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { ProjectSwitcher } from "@/shared/components/ProjectSwitcher";
import { Card } from "@/shared/components/ui/Card";

function toIsoDate(input: Date): string {
  return input.toISOString().slice(0, 10);
}

export function CalendarPage(): JSX.Element {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [activeProjectId, setActiveProjectId] = useState("");
  const [from, setFrom] = useState(toIsoDate(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)));
  const [to, setTo] = useState(toIsoDate(new Date(Date.now() + 14 * 24 * 60 * 60 * 1000)));

  const projectsQuery = useQuery({
    queryKey: ["projects", tenantId],
    queryFn: () => listProjects(tenantId),
    enabled: Boolean(tenantId),
  });

  const calendarQuery = useQuery({
    queryKey: ["calendar", tenantId, activeProjectId, from, to],
    queryFn: () =>
      getCalendar(
        activeProjectId,
        new Date(`${from}T00:00:00.000Z`).toISOString(),
        new Date(`${to}T23:59:59.000Z`).toISOString()
      ),
    enabled: Boolean(tenantId && activeProjectId && from && to),
  });

  const groupedDays = useMemo(() => {
    const map = new Map<string, Array<{ type: "post" | "content"; title?: string | null; status: string; time?: string | null }>>();
    for (const post of calendarQuery.data?.posts ?? []) {
      const date = post.publish_at ? post.publish_at.slice(0, 10) : "unscheduled";
      const row = { type: "post" as const, title: post.title, status: post.status, time: post.publish_at };
      map.set(date, [...(map.get(date) ?? []), row]);
    }
    for (const item of calendarQuery.data?.content_items ?? []) {
      const date = (item.scheduled_for || item.created_at).slice(0, 10);
      const row = {
        type: "content" as const,
        title: item.title,
        status: item.status,
        time: item.scheduled_for || item.created_at,
      };
      map.set(date, [...(map.get(date) ?? []), row]);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [calendarQuery.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Calendar"
        description="Week-style planning list of scheduled posts and content items."
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
        <EmptyState title="Tenant required" description="Set tenant context before using calendar." actionLabel="Open onboarding" onAction={() => navigate("/app/onboarding?step=1")} />
      ) : !activeProjectId ? (
        <EmptyState title="Select project" description="Calendar is project-scoped." actionLabel="Create project" onAction={() => navigate("/app/projects")} />
      ) : (
        <>
          <Card title="Range">
            <div className="grid gap-2 md:grid-cols-2">
              <input
                type="date"
                value={from}
                onChange={(event) => setFrom(event.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
              <input
                type="date"
                value={to}
                onChange={(event) => setTo(event.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
          </Card>

          <Card title="Calendar stream">
            {groupedDays.length === 0 ? (
              <EmptyState title="No events in range" description="Schedule content or posts to populate calendar." />
            ) : (
              <div className="space-y-3">
                {groupedDays.map(([day, items]) => (
                  <div key={day} className="rounded-md border border-slate-200 p-3">
                    <div className="mb-2 font-semibold text-slate-900">{day}</div>
                    <div className="space-y-2">
                      {items.map((row, index) => (
                        <div key={`${day}-${index}`} className="flex items-center justify-between rounded bg-slate-50 px-3 py-2 text-sm">
                          <div>
                            <span className="font-medium text-slate-800">{row.title || "Untitled"}</span>
                            <span className="ml-2 text-xs text-slate-500">({row.type})</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="rounded bg-slate-200 px-2 py-0.5 text-xs text-slate-700">{row.status}</span>
                            <span className="text-xs text-slate-500">{row.time ? new Date(row.time).toLocaleTimeString() : "-"}</span>
                          </div>
                        </div>
                      ))}
                    </div>
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
