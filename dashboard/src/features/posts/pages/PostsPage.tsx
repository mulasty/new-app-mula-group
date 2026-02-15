import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { createPost, listPosts } from "@/shared/api/postsApi";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Input } from "@/shared/components/ui/Input";

export function PostsPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = useTenant();

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [status, setStatus] = useState<"draft" | "scheduled" | "published">("draft");
  const [scheduledAt, setScheduledAt] = useState("");
  const [filter, setFilter] = useState<"all" | "draft" | "scheduled" | "published">("all");

  const postsQuery = useQuery({
    queryKey: ["posts", tenantId],
    queryFn: () => listPosts(tenantId),
    enabled: Boolean(tenantId),
  });

  const createMutation = useMutation({
    mutationFn: () => createPost({ title, content, status, scheduled_at: scheduledAt || undefined }, tenantId),
    onSuccess: (created) => {
      queryClient.setQueryData(["posts", tenantId], (current: { items?: unknown[]; source?: string } | undefined) => ({
        items: [created.item, ...(current?.items ?? [])],
        source: created.source,
        backendMissing: created.backendMissing,
      }));
      setTitle("");
      setContent("");
      setStatus("draft");
      setScheduledAt("");
    },
  });

  const rows = postsQuery.data?.items ?? [];
  const visibleRows = useMemo(
    () => (filter === "all" ? rows : rows.filter((row) => row.status === filter)),
    [rows, filter]
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Posts" description="Create and schedule posts for connected channels." />

      {!tenantId ? (
        <EmptyState
          title="Tenant is required"
          description="Set tenant context before creating posts."
          actionLabel="Open onboarding"
          onAction={() => navigate("/app/onboarding?step=1")}
        />
      ) : (
        <>
          <Card title="Create post">
            <div className="grid gap-3">
              <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Title" />
              <textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                className="min-h-24 rounded-md border border-slate-300 px-3 py-2 text-sm"
                placeholder="Content"
              />
              <div className="grid gap-3 md:grid-cols-3">
                <select
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                  value={status}
                  onChange={(event) => setStatus(event.target.value as typeof status)}
                >
                  <option value="draft">draft</option>
                  <option value="scheduled">scheduled</option>
                  <option value="published">published</option>
                </select>
                <Input type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} />
                <Button
                  type="button"
                  disabled={!title.trim() || !content.trim() || createMutation.isPending}
                  onClick={() => createMutation.mutate()}
                >
                  {createMutation.isPending ? "Saving..." : "Save post"}
                </Button>
              </div>
            </div>
          </Card>

          {postsQuery.data?.backendMissing ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              Backend endpoint missing. Showing mock posts from local storage.
            </div>
          ) : null}

          <Card title="Post list">
            <div className="mb-3 flex gap-2">
              {["all", "draft", "scheduled", "published"].map((value) => (
                <Button
                  key={value}
                  type="button"
                  className={filter === value ? "" : "bg-slate-600 hover:bg-slate-500"}
                  onClick={() => setFilter(value as typeof filter)}
                >
                  {value}
                </Button>
              ))}
            </div>

            {visibleRows.length === 0 ? (
              <EmptyState
                title="No posts"
                description="Create your first post to unlock scheduling insights."
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
                      <th className="py-2">Scheduled</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRows.map((row) => (
                      <tr key={row.id} className="border-t border-slate-200">
                        <td className="py-2">{row.title}</td>
                        <td className="py-2 capitalize">{row.status}</td>
                        <td className="py-2">{row.scheduled_at ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
