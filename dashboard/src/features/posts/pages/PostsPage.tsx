import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { ErrorBadge } from "@/features/posts/components/ErrorBadge";
import { PostEditorModal } from "@/features/posts/components/PostEditorModal";
import { ScheduleModal } from "@/features/posts/components/ScheduleModal";
import { StatusChip } from "@/features/posts/components/StatusChip";
import { TimelineDrawer } from "@/features/posts/components/TimelineDrawer";
import { usePublishingWatcher } from "@/features/posts/hooks/usePublishingWatcher";
import { listWebsitePublications } from "@/shared/api/websitePublicationsApi";
import {
  createPost,
  getTimeline,
  listPosts,
  publishNow,
  schedulePost,
  updatePost,
} from "@/shared/api/postsApi";
import { listChannels, updateChannelStatus } from "@/shared/api/channelsApi";
import { getApiErrorMessage, isEndpointMissing } from "@/shared/api/errors";
import { listProjects } from "@/shared/api/projectsApi";
import { ListResult, PostItem, PostStatus } from "@/shared/api/types";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { ProjectSwitcher } from "@/shared/components/ProjectSwitcher";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Modal } from "@/shared/components/ui/Modal";
import { Spinner } from "@/shared/components/ui/Spinner";
import { getActiveProjectId } from "@/shared/utils/storage";
import { WebsiteFeedPage } from "@/features/posts/pages/WebsiteFeedPage";

type StatusFilter = "all" | PostStatus;
type SortKey = "publish_at" | "updated_at";
type SortDirection = "asc" | "desc";

export function PostsPage(): JSX.Element {
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const { tenantId } = useTenant();

  const [activeProjectId, setActiveProject] = useState("");
  const [tab, setTab] = useState<"posts" | "website-feed">("posts");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("publish_at");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editingPost, setEditingPost] = useState<PostItem | null>(null);
  const [scheduleTarget, setScheduleTarget] = useState<PostItem | null>(null);
  const [timelineTarget, setTimelineTarget] = useState<PostItem | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ type: "cancel" | "retry"; post: PostItem } | null>(null);
  const [updatingChannelId, setUpdatingChannelId] = useState<string | null>(null);

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

  const publicationsQuery = useQuery({
    queryKey: ["websitePublications", tenantId, activeProjectId],
    queryFn: () => listWebsitePublications(tenantId, activeProjectId),
    enabled: Boolean(tenantId && activeProjectId),
  });

  const timelineQuery = useQuery({
    queryKey: ["postTimeline", tenantId, timelineTarget?.id],
    queryFn: () => getTimeline(timelineTarget!.id, tenantId),
    enabled: Boolean(tenantId && timelineTarget?.id),
  });

  const postsQueryKey = useMemo(
    () => ["posts", tenantId, activeProjectId] as const,
    [tenantId, activeProjectId]
  );

  const optimisticPatchPost = useCallback(
    (postId: string, patch: Partial<PostItem>) => {
      queryClient.setQueryData<ListResult<PostItem>>(postsQueryKey, (current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          items: current.items.map((post) => (post.id === postId ? { ...post, ...patch } : post)),
        };
      });
    },
    [queryClient, postsQueryKey]
  );

  const invalidatePostQueries = useCallback(
    (postId?: string) => {
      queryClient.invalidateQueries({ queryKey: ["posts", tenantId, activeProjectId] });
      queryClient.invalidateQueries({ queryKey: ["websitePublications", tenantId, activeProjectId] });
      queryClient.invalidateQueries({ queryKey: ["analyticsSummary", tenantId, activeProjectId] });
      queryClient.invalidateQueries({ queryKey: ["analyticsTimeseries", tenantId, activeProjectId] });
      queryClient.invalidateQueries({ queryKey: ["analyticsActivity", tenantId, activeProjectId] });
      if (postId) {
        queryClient.invalidateQueries({ queryKey: ["postTimeline", tenantId, postId] });
      }
    },
    [activeProjectId, queryClient, tenantId]
  );

  const createMutation = useMutation({
    mutationFn: (values: { title: string; content: string }) =>
      createPost(
        {
          project_id: activeProjectId,
          title: values.title,
          content: values.content,
          status: "draft",
        },
        tenantId
      ),
    onSuccess: (created) => {
      queryClient.setQueryData<ListResult<PostItem>>(postsQueryKey, (current) => ({
        items: [created.item, ...(current?.items ?? [])],
        source: created.source,
        backendMissing: created.backendMissing,
      }));
      invalidatePostQueries(created.item.id);
      setCreateModalOpen(false);
      pushToast("Post created", "success");
    },
    onError: (error) => {
      pushToast(getApiErrorMessage(error, "Failed to create post"), "error");
    },
  });

  const updateMutation = useMutation({
    mutationFn: (payload: { postId: string; title: string; content: string }) =>
      updatePost(
        payload.postId,
        {
          title: payload.title,
          content: payload.content,
        },
        tenantId
      ),
    onSuccess: (updated) => {
      optimisticPatchPost(updated.item.id, updated.item);
      invalidatePostQueries(updated.item.id);
      setEditingPost(null);
      pushToast("Post updated", "success");
    },
    onError: (error) => {
      pushToast(getApiErrorMessage(error, "Failed to update post"), "error");
    },
  });

  const scheduleMutation = useMutation({
    mutationFn: (payload: { postId: string; publishAtIso: string }) =>
      schedulePost(payload.postId, payload.publishAtIso, tenantId),
    onMutate: (payload) => {
      optimisticPatchPost(payload.postId, {
        status: "scheduled",
        publish_at: payload.publishAtIso,
      });
    },
    onSuccess: (updated) => {
      setScheduleTarget(null);
      invalidatePostQueries(updated.item.id);
      pushToast("Post scheduled", "success");
    },
    onError: (error) => {
      invalidatePostQueries();
      pushToast(getApiErrorMessage(error, "Failed to schedule post"), "error");
    },
  });

  const publishNowMutation = useMutation({
    mutationFn: (postId: string) => publishNow(postId, tenantId),
    onMutate: (postId) => {
      optimisticPatchPost(postId, { status: "publishing" });
    },
    onSuccess: (updated) => {
      window.setTimeout(() => {
        invalidatePostQueries(updated.item.id);
      }, 800);
      pushToast("Publish requested", "success");
    },
    onError: (error) => {
      invalidatePostQueries();
      pushToast(getApiErrorMessage(error, "Failed to publish now"), "error");
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (postId: string) =>
      updatePost(
        postId,
        {
          status: "draft",
          publish_at: null,
        },
        tenantId
      ),
    onMutate: (postId) => {
      optimisticPatchPost(postId, { status: "draft", publish_at: null });
    },
    onSuccess: (updated) => {
      setConfirmAction(null);
      invalidatePostQueries(updated.item.id);
      pushToast("Schedule canceled", "success");
    },
    onError: (error) => {
      invalidatePostQueries();
      pushToast(getApiErrorMessage(error, "Failed to cancel schedule"), "error");
    },
  });

  const retryMutation = useMutation({
    mutationFn: (postId: string) => schedulePost(postId, new Date().toISOString(), tenantId),
    onMutate: (postId) => {
      optimisticPatchPost(postId, { status: "scheduled", publish_at: new Date().toISOString() });
    },
    onSuccess: (updated) => {
      setConfirmAction(null);
      invalidatePostQueries(updated.item.id);
      pushToast("Retry queued", "success");
    },
    onError: (error) => {
      invalidatePostQueries();
      pushToast(getApiErrorMessage(error, "Failed to retry post"), "error");
    },
  });

  const channelStatusMutation = useMutation({
    mutationFn: (payload: { channelId: string; status: "active" | "disabled" }) =>
      updateChannelStatus(payload.channelId, payload.status),
    onMutate: ({ channelId }) => {
      setUpdatingChannelId(channelId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["channels", tenantId, activeProjectId] });
      pushToast("Publishing channels updated", "success");
    },
    onError: (error) => {
      pushToast(getApiErrorMessage(error, "Failed to update channel status"), "error");
    },
    onSettled: () => {
      setUpdatingChannelId(null);
    },
  });

  const rows = postsQuery.data?.items ?? [];
  const publishingPostId = useMemo(
    () => rows.find((post) => post.status === "publishing")?.id,
    [rows]
  );
  const watchedPostId = timelineTarget?.id ?? publishingPostId;
  usePublishingWatcher({
    postId: watchedPostId,
    tenantId,
    projectId: activeProjectId,
  });

  const endpointMissing =
    isEndpointMissing(postsQuery.error) ||
    isEndpointMissing(createMutation.error) ||
    isEndpointMissing(updateMutation.error);

  const channels = channelsQuery.data?.items ?? [];
  const activeChannels = channels.filter((channel) => (channel.status ?? "active") !== "disabled");
  const hasActiveChannel = activeChannels.length > 0;
  const hasTextPublishingSupport = activeChannels.some(
    (channel) => (channel.capabilities_json?.text ?? true) === true
  );

  const visibleRows = useMemo(() => {
    let next = [...rows];

    if (statusFilter !== "all") {
      next = next.filter((row) => row.status === statusFilter);
    }

    if (search.trim()) {
      const searchNormalized = search.trim().toLowerCase();
      next = next.filter((row) => row.title.toLowerCase().includes(searchNormalized));
    }

    const sortFactor = sortDirection === "asc" ? 1 : -1;
    next.sort((a, b) => {
      const aDate =
        sortKey === "publish_at"
          ? new Date(a.publish_at ?? 0).getTime()
          : new Date(a.updated_at ?? a.created_at ?? 0).getTime();
      const bDate =
        sortKey === "publish_at"
          ? new Date(b.publish_at ?? 0).getTime()
          : new Date(b.updated_at ?? b.created_at ?? 0).getTime();
      return (aDate - bDate) * sortFactor;
    });

    return next;
  }, [rows, statusFilter, search, sortKey, sortDirection]);

  const projects = projectsQuery.data?.items ?? [];

  const projectActions = (
    <ProjectSwitcher
      tenantId={tenantId}
      projects={projects}
      value={activeProjectId}
      onChange={setActiveProject}
      disabled={projectsQuery.isLoading}
    />
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Posts"
        description="Publishing console for drafting, scheduling and tracking deliveries."
        actions={projectActions}
      />

      {!tenantId ? (
        <EmptyState
          title="Tenant is required"
          description="Set tenant context before creating posts."
          actionLabel="Open onboarding"
          onAction={() => navigate("/app/onboarding?step=1")}
        />
      ) : (
        <>
          {!activeProjectId ? (
            <EmptyState
              title="Select or create a project"
              description="Publishing console needs an active project context."
              actionLabel="Go to onboarding"
              onAction={() => navigate("/app/onboarding?step=2")}
            />
          ) : null}

          {activeProjectId && !hasActiveChannel ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              No active channel for this project. Connect a channel before publishing posts.
              <button
                type="button"
                className="ml-2 underline"
                onClick={() => navigate("/app/channels")}
              >
                Go to channels
              </button>
            </div>
          ) : null}

          {activeProjectId && channels.length > 0 ? (
            <Card title="Publishing targets">
              <div className="grid gap-2 md:grid-cols-2">
                {channels.map((channel) => {
                  const isActive = (channel.status ?? "active") !== "disabled";
                  return (
                    <label
                      key={channel.id}
                      className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2"
                    >
                      <div>
                        <div className="text-sm font-medium text-slate-900">{channel.name ?? channel.type}</div>
                        <div className="text-xs text-slate-500">{channel.type}</div>
                      </div>
                      <input
                        type="checkbox"
                        checked={isActive}
                        disabled={channelStatusMutation.isPending && updatingChannelId === channel.id}
                        onChange={(event) =>
                          channelStatusMutation.mutate({
                            channelId: channel.id,
                            status: event.target.checked ? "active" : "disabled",
                          })
                        }
                      />
                    </label>
                  );
                })}
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Only active channels receive publish jobs for this project.
              </p>
            </Card>
          ) : null}

          {activeProjectId && hasActiveChannel && !hasTextPublishingSupport ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              Active channels do not support text publishing. Connect a channel with Text capability.
            </div>
          ) : null}

          {(postsQuery.data?.backendMissing || publicationsQuery.data?.backendMissing) ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              Endpoint not available yet. Fallback data is active because `enableMockFallback` is enabled.
            </div>
          ) : null}

          {endpointMissing ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              Endpoint not available yet. Enable mock fallback to continue testing without backend route.
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              className={tab === "posts" ? "" : "bg-slate-600 hover:bg-slate-500"}
              onClick={() => setTab("posts")}
            >
              Posts
            </Button>
            <Button
              type="button"
              className={tab === "website-feed" ? "" : "bg-slate-600 hover:bg-slate-500"}
              onClick={() => setTab("website-feed")}
            >
              Website feed
            </Button>
          </div>

          {tab === "posts" ? (
            <Card title="Publishing console">
              {activeProjectId ? (
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    {(
                      ["all", "draft", "scheduled", "publishing", "published", "published_partial", "failed"] as StatusFilter[]
                    ).map(
                      (value) => (
                        <Button
                          key={value}
                          type="button"
                          className={statusFilter === value ? "" : "bg-slate-600 hover:bg-slate-500"}
                          onClick={() => setStatusFilter(value)}
                        >
                          {value}
                        </Button>
                      )
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Search title"
                      className="min-w-56 rounded-md border border-slate-300 px-3 py-2 text-sm"
                    />
                    <select
                      value={sortKey}
                      onChange={(event) => setSortKey(event.target.value as SortKey)}
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                    >
                      <option value="publish_at">Sort by publish_at</option>
                      <option value="updated_at">Sort by updated_at</option>
                    </select>
                    <select
                      value={sortDirection}
                      onChange={(event) => setSortDirection(event.target.value as SortDirection)}
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                    >
                      <option value="desc">Newest first</option>
                      <option value="asc">Oldest first</option>
                    </select>
                    <Button
                      type="button"
                      disabled={!hasTextPublishingSupport}
                      onClick={() => setCreateModalOpen(true)}
                    >
                      Create post
                    </Button>
                  </div>
                </div>
              ) : null}

              {postsQuery.isLoading || channelsQuery.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-slate-600">
                  <Spinner /> Loading posts...
                </div>
              ) : visibleRows.length === 0 ? (
                <EmptyState
                  title="No posts for selected project"
                  description="Create your first post and start the publishing flow."
                  actionLabel="Open onboarding"
                  onAction={() => navigate("/app/onboarding?step=4")}
                />
              ) : (
                <div className="overflow-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="text-slate-500">
                      <tr>
                        <th className="py-2">Title</th>
                        <th className="py-2">Status</th>
                        <th className="py-2">Publish at</th>
                        <th className="py-2">Updated</th>
                        <th className="py-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleRows.map((row) => {
                        const isPublishing = row.status === "publishing";
                        const canEdit = row.status === "draft";
                        const canSchedule =
                          hasTextPublishingSupport && (row.status === "draft" || row.status === "scheduled");
                        const canPublishNow =
                          hasTextPublishingSupport && (row.status === "draft" || row.status === "scheduled");
                        return (
                          <tr key={row.id} className="border-t border-slate-200 align-top">
                            <td className="py-2">
                              <div className="font-medium text-slate-900">{row.title}</div>
                              <div className="max-w-xl truncate text-xs text-slate-500">{row.content}</div>
                            </td>
                            <td className="py-2">
                              <div className="flex items-center gap-2">
                                {isPublishing ? <Spinner className="h-3.5 w-3.5" /> : null}
                                <StatusChip status={row.status} />
                              </div>
                              {row.status === "failed" ? <ErrorBadge message={row.last_error} /> : null}
                            </td>
                            <td className="py-2 text-slate-600">
                              {row.publish_at ? new Date(row.publish_at).toLocaleString() : "-"}
                            </td>
                            <td className="py-2 text-slate-600">
                              {row.updated_at ? new Date(row.updated_at).toLocaleString() : "-"}
                            </td>
                            <td className="py-2">
                              <div className="flex flex-wrap gap-2">
                                <Button
                                  type="button"
                                  className="bg-slate-700 px-3 py-1 text-xs hover:bg-slate-600"
                                  disabled={!canEdit || isPublishing}
                                  onClick={() => setEditingPost(row)}
                                >
                                  Edit
                                </Button>
                                <Button
                                  type="button"
                                  className="bg-slate-700 px-3 py-1 text-xs hover:bg-slate-600"
                                  disabled={!canSchedule || isPublishing}
                                  onClick={() => setScheduleTarget(row)}
                                >
                                  {row.status === "scheduled" ? "Reschedule" : "Schedule"}
                                </Button>
                                <Button
                                  type="button"
                                  className="bg-slate-700 px-3 py-1 text-xs hover:bg-slate-600"
                                  disabled={!canPublishNow || isPublishing || publishNowMutation.isPending}
                                  onClick={() => publishNowMutation.mutate(row.id)}
                                >
                                  Publish now
                                </Button>
                                {row.status === "scheduled" ? (
                                  <Button
                                    type="button"
                                    className="bg-rose-600 px-3 py-1 text-xs hover:bg-rose-500"
                                    disabled={cancelMutation.isPending}
                                    onClick={() => setConfirmAction({ type: "cancel", post: row })}
                                  >
                                    Cancel schedule
                                  </Button>
                                ) : null}
                                {row.status === "failed" || row.status === "published_partial" ? (
                                  <Button
                                    type="button"
                                    className="bg-amber-600 px-3 py-1 text-xs hover:bg-amber-500"
                                    disabled={retryMutation.isPending}
                                    onClick={() => setConfirmAction({ type: "retry", post: row })}
                                  >
                                    Retry
                                  </Button>
                                ) : null}
                                <Button
                                  type="button"
                                  className="bg-slate-200 px-3 py-1 text-xs text-slate-700 hover:bg-slate-300"
                                  onClick={() => setTimelineTarget(row)}
                                >
                                  Timeline
                                </Button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          ) : (
            <WebsiteFeedPage
              publications={publicationsQuery.data?.items ?? []}
              isLoading={publicationsQuery.isLoading}
              backendMissing={publicationsQuery.data?.backendMissing}
              endpointUnavailable={isEndpointMissing(publicationsQuery.error)}
              onOpenOnboarding={() => navigate("/app/onboarding?step=4")}
            />
          )}

          <PostEditorModal
            open={createModalOpen}
            title="Create post"
            onClose={() => setCreateModalOpen(false)}
            isSubmitting={createMutation.isPending}
            onSubmit={(values) => createMutation.mutate(values)}
          />

          <PostEditorModal
            open={Boolean(editingPost)}
            title="Edit post"
            initialValues={{
              title: editingPost?.title ?? "",
              content: editingPost?.content ?? "",
            }}
            onClose={() => setEditingPost(null)}
            isSubmitting={updateMutation.isPending}
            onSubmit={(values) => {
              if (!editingPost) {
                return;
              }
              updateMutation.mutate({
                postId: editingPost.id,
                title: values.title,
                content: values.content,
              });
            }}
          />

          <ScheduleModal
            open={Boolean(scheduleTarget)}
            title={scheduleTarget?.status === "scheduled" ? "Reschedule post" : "Schedule post"}
            initialPublishAt={scheduleTarget?.publish_at}
            isSubmitting={scheduleMutation.isPending}
            onClose={() => setScheduleTarget(null)}
            onSubmit={(publishAtIso) => {
              if (!scheduleTarget) {
                return;
              }
              scheduleMutation.mutate({ postId: scheduleTarget.id, publishAtIso });
            }}
          />

          <Modal
            open={Boolean(confirmAction)}
            title={confirmAction?.type === "retry" ? "Retry failed post?" : "Cancel scheduled post?"}
            onClose={() => setConfirmAction(null)}
            footer={
              <>
                <Button
                  type="button"
                  className="bg-slate-200 text-slate-700 hover:bg-slate-300"
                  onClick={() => setConfirmAction(null)}
                >
                  Keep current
                </Button>
                <Button
                  type="button"
                  className={
                    confirmAction?.type === "retry"
                      ? "bg-amber-600 hover:bg-amber-500"
                      : "bg-rose-600 hover:bg-rose-500"
                  }
                  onClick={() => {
                    if (!confirmAction) {
                      return;
                    }
                    if (confirmAction.type === "retry") {
                      retryMutation.mutate(confirmAction.post.id);
                    } else {
                      cancelMutation.mutate(confirmAction.post.id);
                    }
                  }}
                >
                  {confirmAction?.type === "retry" ? "Retry now" : "Cancel schedule"}
                </Button>
              </>
            }
          >
            <p className="text-sm text-slate-600">
              {confirmAction?.type === "retry"
                ? "This will reschedule the failed post for immediate publishing."
                : "This action moves the post back to draft status."}
            </p>
          </Modal>

          <TimelineDrawer
            open={Boolean(timelineTarget)}
            postTitle={timelineTarget?.title}
            items={timelineQuery.data?.items ?? []}
            isLoading={timelineQuery.isLoading}
            backendMissing={timelineQuery.data?.backendMissing}
            errorMessage={
              timelineQuery.error
                ? isEndpointMissing(timelineQuery.error)
                  ? "Endpoint not available yet."
                  : getApiErrorMessage(timelineQuery.error)
                : null
            }
            onClose={() => setTimelineTarget(null)}
          />
        </>
      )}
    </div>
  );
}
