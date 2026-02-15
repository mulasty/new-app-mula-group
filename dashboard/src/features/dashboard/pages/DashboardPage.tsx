import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { useOnboardingStatus } from "@/features/onboarding/hooks/useOnboardingStatus";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";

export function DashboardPage(): JSX.Element {
  const navigate = useNavigate();
  const {
    isOnboardingRequired,
    showSoftReminder,
    recommendedStep,
    projectsQuery,
    channelsQuery,
    postsQuery,
  } = useOnboardingStatus();

  const posts = postsQuery.data?.items ?? [];
  const metrics = useMemo(
    () => ({
      scheduled: posts.filter((post) => post.status === "scheduled").length,
      published: posts.filter((post) => post.status === "published").length,
      failed: 0,
    }),
    [posts]
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" description="Operational overview for your tenant." />

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
            <ul className="space-y-2 text-sm text-slate-600">
              <li>Post scheduled for tomorrow at 09:00</li>
              <li>Project created by owner</li>
              <li>Channel connected and credentials saved</li>
            </ul>
          </Card>
        </>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Projects">
          {(projectsQuery.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No projects"
              description="Create a project to organize your publishing workflows."
              actionLabel="Add project"
              onAction={() => navigate("/app/projects")}
            />
          ) : (
            <div className="text-sm text-slate-600">{projectsQuery.data?.items.length} projects available.</div>
          )}
        </Card>

        <Card title="Channels">
          {(channelsQuery.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No channels"
              description="Connect at least one channel before scheduling posts."
              actionLabel="Connect channel"
              onAction={() => navigate("/app/channels")}
            />
          ) : (
            <div className="text-sm text-slate-600">{channelsQuery.data?.items.length} channels connected.</div>
          )}
        </Card>

        <Card title="Posts">
          {(postsQuery.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No posts"
              description="Create first post and start testing your publishing pipeline."
              actionLabel="Create post"
              onAction={() => navigate("/app/posts")}
            />
          ) : (
            <div className="text-sm text-slate-600">{postsQuery.data?.items.length} posts in workspace.</div>
          )}
        </Card>
      </div>
    </div>
  );
}
