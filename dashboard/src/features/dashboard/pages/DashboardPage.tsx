import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useOnboardingStatus } from "@/features/onboarding/hooks/useOnboardingStatus";
import { ActivityStream } from "@/features/dashboard/components/ActivityStream";
import { AnalyticsKpiCards } from "@/features/dashboard/components/AnalyticsKpiCards";
import { PublishingChart } from "@/features/dashboard/components/PublishingChart";
import {
  getActivityStream,
  getPublishingSummary,
  getPublishingTimeseries,
} from "@/shared/api/analyticsApi";
import { createCheckoutSession, getCurrentBilling } from "@/shared/api/billingApi";
import { getApiErrorMessage, isEndpointMissing } from "@/shared/api/errors";
import { listProjects } from "@/shared/api/projectsApi";
import { PublishingTimeRange } from "@/shared/api/types";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { ProjectSwitcher } from "@/shared/components/ProjectSwitcher";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { getActiveProjectId } from "@/shared/utils/storage";

type DashboardTab = "overview" | "publishing" | "activity";

function buildAnalyticsErrorMessage(error: unknown, fallback: string): string | null {
  if (!error) {
    return null;
  }
  if (isEndpointMissing(error)) {
    return "Endpoint not available yet.";
  }
  return getApiErrorMessage(error, fallback);
}

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
  const [activeTab, setActiveTab] = useState<DashboardTab>("overview");
  const [range, setRange] = useState<PublishingTimeRange>("7d");

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

  const summaryQuery = useQuery({
    queryKey: ["analyticsSummary", tenantId, activeProjectId],
    queryFn: () => getPublishingSummary({ projectId: activeProjectId }),
    enabled: Boolean(tenantId && activeProjectId),
    refetchInterval: 60000,
  });

  const timeseriesQuery = useQuery({
    queryKey: ["analyticsTimeseries", tenantId, activeProjectId, range],
    queryFn: () => getPublishingTimeseries({ projectId: activeProjectId, range }),
    enabled: Boolean(tenantId && activeProjectId),
    refetchInterval: 60000,
  });

  const activityQuery = useQuery({
    queryKey: ["analyticsActivity", tenantId, activeProjectId, 50],
    queryFn: () => getActivityStream({ projectId: activeProjectId, limit: 50 }),
    enabled: Boolean(tenantId && activeProjectId),
    refetchInterval: 60000,
  });
  const billingQuery = useQuery({
    queryKey: ["billingCurrent", tenantId],
    queryFn: () => getCurrentBilling(),
    enabled: Boolean(tenantId),
  });

  const projectActions = (
    <ProjectSwitcher
      tenantId={tenantId}
      projects={projectsQuery.data?.items ?? []}
      value={activeProjectId}
      onChange={setActiveProject}
      disabled={projectsQuery.isLoading}
    />
  );

  const summaryError = useMemo(
    () => buildAnalyticsErrorMessage(summaryQuery.error, "Failed to load publishing summary"),
    [summaryQuery.error]
  );
  const timeseriesError = useMemo(
    () => buildAnalyticsErrorMessage(timeseriesQuery.error, "Failed to load publishing chart"),
    [timeseriesQuery.error]
  );
  const activityError = useMemo(
    () => buildAnalyticsErrorMessage(activityQuery.error, "Failed to load activity stream"),
    [activityQuery.error]
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
      ) : !activeProjectId ? (
        <EmptyState
          title="Select project to load analytics"
          description="Choose an active project to view publishing performance."
          actionLabel="Go to projects"
          onAction={() => navigate("/app/projects")}
        />
      ) : (
        <>
          {billingQuery.data ? (
            <Card className="border-indigo-200 bg-indigo-50">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm text-indigo-900">
                  Plan <span className="font-semibold">{billingQuery.data.plan.name}</span>:{" "}
                  {billingQuery.data.usage.posts_used_current_period}/{billingQuery.data.plan.max_posts_per_month} posts used.
                </div>
                {billingQuery.data.plan.name.toLowerCase() !== "enterprise" ? (
                  <Button
                    type="button"
                    onClick={async () => {
                      try {
                        const response = await createCheckoutSession("Enterprise");
                        if (response.checkout_url) {
                          window.location.assign(response.checkout_url);
                        }
                      } catch {
                        // ignored - global api interceptor and page toasts cover feedback.
                      }
                    }}
                  >
                    Upgrade plan
                  </Button>
                ) : null}
              </div>
            </Card>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              className={activeTab === "overview" ? "" : "bg-slate-600 hover:bg-slate-500"}
              onClick={() => setActiveTab("overview")}
            >
              Overview
            </Button>
            <Button
              type="button"
              className={activeTab === "publishing" ? "" : "bg-slate-600 hover:bg-slate-500"}
              onClick={() => setActiveTab("publishing")}
            >
              Publishing
            </Button>
            <Button
              type="button"
              className={activeTab === "activity" ? "" : "bg-slate-600 hover:bg-slate-500"}
              onClick={() => setActiveTab("activity")}
            >
              Activity
            </Button>
          </div>

          {activeTab === "overview" ? (
            <>
              <AnalyticsKpiCards
                data={summaryQuery.data}
                isLoading={summaryQuery.isLoading}
                errorMessage={summaryError}
              />
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
                    <div className="text-sm text-slate-600">
                      {onboardingProjectsQuery.data?.items.length} projects available.
                    </div>
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
                    <div className="text-sm text-slate-600">
                      {onboardingChannelsQuery.data?.items.length} channels connected.
                    </div>
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
                    <div className="text-sm text-slate-600">
                      {onboardingPostsQuery.data?.items.length} posts in workspace.
                    </div>
                  )}
                </Card>
              </div>
            </>
          ) : null}

          {activeTab === "publishing" ? (
            <>
              <AnalyticsKpiCards
                data={summaryQuery.data}
                isLoading={summaryQuery.isLoading}
                errorMessage={summaryError}
              />
              <PublishingChart
                points={timeseriesQuery.data ?? []}
                range={range}
                onRangeChange={setRange}
                isLoading={timeseriesQuery.isLoading}
                errorMessage={timeseriesError}
              />
            </>
          ) : null}

          {activeTab === "activity" ? (
            <ActivityStream
              items={activityQuery.data ?? []}
              isLoading={activityQuery.isLoading}
              errorMessage={activityError}
            />
          ) : null}
        </>
      )}
    </div>
  );
}
