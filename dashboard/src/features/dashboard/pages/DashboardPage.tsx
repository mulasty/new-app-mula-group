import { useEffect, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useOnboardingStatus } from "@/features/onboarding/hooks/useOnboardingStatus";
import { listChannels } from "@/shared/api/channelsApi";
import { isEndpointMissing } from "@/shared/api/errors";
import { getTimeline, listPosts } from "@/shared/api/postsApi";
import { listProjects } from "@/shared/api/projectsApi";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { ProjectSwitcher } from "@/shared/components/ProjectSwitcher";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Spinner } from "@/shared/components/ui/Spinner";
import { getActiveProjectId } from "@/shared/utils/storage";

export function DashboardPage(): JSX.Element {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const {
    isOnboardingRequired,
    showSoftReminder,
    recommendedStep,
    projectsQuery: onboardingProjectsQuery,
    channelsQuery: onboardingChannelsQuery,
    postsQuery: onboardingPostsQuery,
  } = useOnboardingStatus();

  const [activeProjectId, setActiveProject] = useState("");

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

  const postsQuery = useQuery({
    queryKey: ["posts", tenantId, activeProjectId],
    queryFn: () => listPosts(tenantId, activeProjectId),
    enabled: Boolean(tenantId && activeProjectId),
  });

  const channelsQuery = useQuery({
    queryKey: ["channels", tenantId, activeProjectId],
    queryFn: () => listChannels(tenantId, activeProjectId),
    enabled: Boolean(tenantId && activeProjectId),
  });

  const posts = postsQuery.data?.items ?? [];
  const metrics = useMemo(
    () => ({
      scheduled: posts.filter((post) => post.status === "scheduled").length,
      published: posts.filter((post) => post.status === "published").length,
      failed: posts.filter((post) => post.status === "failed").length,
    }),
    [posts]
  );

  const recentPostIds = useMemo(() => posts.slice(0, 5).map((post) => post.id), [posts]);
  const timelineQueries = useQueries({
    queries: recentPostIds.map((postId) => ({
      queryKey: ["postTimeline", tenantId, postId],
      queryFn: () => getTimeline(postId, tenantId),
      enabled: Boolean(tenantId && activeProjectId),
    })),
  });

  const recentEvents = useMemo(() => {
    const aggregated = timelineQueries
      .map((query) => query.data?.items ?? [])
      .flat()
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    return aggregated.slice(0, 8);
  }, [timelineQueries]);

  const projectActions = (
    <ProjectSwitcher
      tenantId={tenantId}
      projects={projectsQuery.data?.items ?? []}
      value={activeProjectId}
      onChange={setActiveProject}
      disabled={projectsQuery.isLoading}
    />
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" description="Operational overview for your tenant." actions={projectActions} />

      {isOnboardingRequired ? (
        <Card className="border-brand-200 bg-brand-50">
          <h2 className="text-xl font-semibold text-brand-900">Dokoncz konfiguracje</h2>
          <p className="mt-1 text-sm text-brand-900/80">
            Skonfiguruj tenant i pierwszy content flow, aby od razu zobaczyc wartosc produktu.
          </p>
          {showSoftReminder ? (
            <div className="mt-2 text-xs text-brand-800">You skipped onboarding earlier. Continue when ready.</div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="button" onClick={() => navigate(`/app/onboarding?step=${recommendedStep}`)}>
              Kontynuuj onboarding
            </Button>
            <Button type="button" className="bg-slate-700 hover:bg-slate-600" onClick={() => navigate("/app/posts")}>
              Utworz pierwszy post
            </Button>
          </div>
        </Card>
      ) : (
        <>
          {!activeProjectId ? (
            <EmptyState
              title="Select project to load KPIs"
              description="Choose an active project to view publishing metrics."
              actionLabel="Go to projects"
              onAction={() => navigate("/app/projects")}
            />
          ) : null}

          {(postsQuery.isLoading || channelsQuery.isLoading) && activeProjectId ? (
            <Card>
              <div className="flex items-center gap-2 text-sm text-slate-600">
                <Spinner /> Loading project metrics...
              </div>
            </Card>
          ) : null}

          {isEndpointMissing(postsQuery.error) ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              Endpoint not available yet. Post metrics may be incomplete.
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <div className="text-sm text-slate-500">Scheduled</div>
              <div className="mt-1 text-3xl font-bold text-slate-900">{metrics.scheduled}</div>
            </Card>
            <Card>
              <div className="text-sm text-slate-500">Published</div>
              <div className="mt-1 text-3xl font-bold text-slate-900">{metrics.published}</div>
            </Card>
            <Card>
              <div className="text-sm text-slate-500">Failed</div>
              <div className="mt-1 text-3xl font-bold text-slate-900">{metrics.failed}</div>
            </Card>
          </div>

          <Card title="Recent activity">
            {recentEvents.length === 0 ? (
              <div className="text-sm text-slate-600">
                Recent publish activity will appear here after posts move through schedule/publish lifecycle.
              </div>
            ) : (
              <ul className="space-y-2 text-sm text-slate-600">
                {recentEvents.map((event) => (
                  <li key={event.id} className="rounded-md border border-slate-200 px-3 py-2">
                    <div className="font-medium text-slate-900">{event.event_type}</div>
                    <div className="text-xs text-slate-500">
                      {event.status} | attempt #{event.attempt} | {new Date(event.created_at).toLocaleString()}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Projects">
          {(onboardingProjectsQuery.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No projects"
              description="Create a project to organize your publishing workflows."
              actionLabel="Add project"
              onAction={() => navigate("/app/projects")}
            />
          ) : (
            <div className="text-sm text-slate-600">{onboardingProjectsQuery.data?.items.length} projects available.</div>
          )}
        </Card>

        <Card title="Channels">
          {(onboardingChannelsQuery.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No channels"
              description="Connect at least one channel before scheduling posts."
              actionLabel="Connect channel"
              onAction={() => navigate("/app/channels")}
            />
          ) : (
            <div className="text-sm text-slate-600">{onboardingChannelsQuery.data?.items.length} channels connected.</div>
          )}
        </Card>

        <Card title="Posts">
          {(onboardingPostsQuery.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No posts"
              description="Create first post and start testing your publishing pipeline."
              actionLabel="Create post"
              onAction={() => navigate("/app/posts")}
            />
          ) : (
            <div className="text-sm text-slate-600">{onboardingPostsQuery.data?.items.length} posts in workspace.</div>
          )}
        </Card>
      </div>
    </div>
  );
}
