import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import {
  approveContent,
  createContent,
  createTemplate,
  listContent,
  rejectContent,
  scheduleContent,
  listTemplates,
} from "@/shared/api/automationApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { listProjects } from "@/shared/api/projectsApi";
import { evaluateContentAndAttach } from "@/shared/api/aiQualityApi";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { ProjectSwitcher } from "@/shared/components/ProjectSwitcher";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Input } from "@/shared/components/ui/Input";

export function ContentStudioPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { tenantId } = useTenant();

  const [activeProjectId, setActiveProjectId] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [scheduleAt, setScheduleAt] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [templateCategory, setTemplateCategory] = useState("educational");
  const [templateTone, setTemplateTone] = useState("professional");
  const [templateStructure, setTemplateStructure] = useState("Hook -> insight -> CTA");
  const [templatePrompt, setTemplatePrompt] = useState("Napisz post o {{topic}} z CTA {{offer}}.");
  const [templateSchema, setTemplateSchema] = useState(
    JSON.stringify(
      {
        type: "object",
        required: ["title", "body", "hashtags", "cta", "channels", "risk_flags"],
      },
      null,
      2
    )
  );

  const projectsQuery = useQuery({
    queryKey: ["projects", tenantId],
    queryFn: () => listProjects(tenantId),
    enabled: Boolean(tenantId),
  });

  const templatesQuery = useQuery({
    queryKey: ["templates", tenantId, activeProjectId],
    queryFn: () => listTemplates(activeProjectId),
    enabled: Boolean(tenantId && activeProjectId),
  });

  const contentQuery = useQuery({
    queryKey: ["contentItems", tenantId, activeProjectId],
    queryFn: () => listContent(activeProjectId),
    enabled: Boolean(tenantId && activeProjectId),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createContent({
        project_id: activeProjectId,
        template_id: selectedTemplateId || undefined,
        title: title.trim() || undefined,
        body: body.trim(),
      }),
    onSuccess: () => {
      pushToast("Content item created", "success");
      setTitle("");
      setBody("");
      queryClient.invalidateQueries({ queryKey: ["contentItems", tenantId, activeProjectId] });
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to create content"), "error"),
  });

  const createTemplateMutation = useMutation({
    mutationFn: () =>
      createTemplate({
        project_id: activeProjectId,
        name: templateName.trim(),
        category: templateCategory,
        tone: templateTone,
        content_structure: templateStructure,
        template_type: "post_text",
        prompt_template: templatePrompt,
        output_schema_json: JSON.parse(templateSchema),
      }),
    onSuccess: () => {
      pushToast("Template created", "success");
      setTemplateName("");
      queryClient.invalidateQueries({ queryKey: ["templates", tenantId, activeProjectId] });
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to create template"), "error"),
  });

  const reviewMutation = useMutation({
    mutationFn: ({ contentId, action }: { contentId: string; action: "approve" | "reject" }) =>
      action === "approve" ? approveContent(contentId) : rejectContent(contentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["contentItems", tenantId, activeProjectId] }),
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to review content"), "error"),
  });

  const scheduleMutation = useMutation({
    mutationFn: ({ contentId, publishAt }: { contentId: string; publishAt: string }) => scheduleContent(contentId, publishAt),
    onSuccess: () => {
      pushToast("Content scheduled", "success");
      queryClient.invalidateQueries({ queryKey: ["contentItems", tenantId, activeProjectId] });
      queryClient.invalidateQueries({ queryKey: ["posts", tenantId, activeProjectId] });
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to schedule content"), "error"),
  });
  const qualityMutation = useMutation({
    mutationFn: (contentId: string) => evaluateContentAndAttach(contentId),
    onSuccess: () => {
      pushToast("Quality evaluation completed", "success");
      queryClient.invalidateQueries({ queryKey: ["contentItems", tenantId, activeProjectId] });
    },
    onError: (error) => pushToast(getApiErrorMessage(error, "Failed to evaluate quality"), "error"),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Content Studio"
        description="Review AI/manual content, approve/reject and schedule to publishing pipeline."
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
        <EmptyState title="Tenant required" description="Set tenant context first." actionLabel="Open onboarding" onAction={() => navigate("/app/onboarding?step=1")} />
      ) : !activeProjectId ? (
        <EmptyState title="Select project" description="Content studio is project-scoped." actionLabel="Create project" onAction={() => navigate("/app/projects")} />
      ) : (
        <>
          <Card title="Create manual content item">
            <div className="space-y-2">
              <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Title (optional)" />
              <select
                value={selectedTemplateId}
                onChange={(event) => setSelectedTemplateId(event.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                <option value="">No template</option>
                {(templatesQuery.data ?? []).map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                  </option>
                ))}
              </select>
              <textarea
                value={body}
                onChange={(event) => setBody(event.target.value)}
                placeholder="Content body"
                className="min-h-32 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
              <Button type="button" disabled={!body.trim() || createMutation.isPending} onClick={() => createMutation.mutate()}>
                {createMutation.isPending ? "Creating..." : "Create content item"}
              </Button>
            </div>
          </Card>

          <Card title="Template builder (post_text)">
            <div className="space-y-2">
              <Input
                value={templateName}
                onChange={(event) => setTemplateName(event.target.value)}
                placeholder="Template name"
              />
              <div className="grid gap-2 md:grid-cols-3">
                <select
                  value={templateCategory}
                  onChange={(event) => setTemplateCategory(event.target.value)}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                >
                  <option value="product launch">product launch</option>
                  <option value="educational">educational</option>
                  <option value="social proof">social proof</option>
                  <option value="engagement">engagement</option>
                  <option value="promotional">promotional</option>
                </select>
                <Input value={templateTone} onChange={(event) => setTemplateTone(event.target.value)} placeholder="Tone" />
                <Input
                  value={templateStructure}
                  onChange={(event) => setTemplateStructure(event.target.value)}
                  placeholder="Content structure"
                />
              </div>
              <textarea
                value={templatePrompt}
                onChange={(event) => setTemplatePrompt(event.target.value)}
                className="min-h-24 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                placeholder="Prompt template with variables, e.g. {{topic}}"
              />
              <textarea
                value={templateSchema}
                onChange={(event) => setTemplateSchema(event.target.value)}
                className="min-h-32 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-xs"
                placeholder="Output JSON schema"
              />
              <Button
                type="button"
                disabled={!templateName.trim() || createTemplateMutation.isPending}
                onClick={() => createTemplateMutation.mutate()}
              >
                {createTemplateMutation.isPending ? "Saving..." : "Save template"}
              </Button>
            </div>
          </Card>

          <Card title="Content queue">
            {(contentQuery.data?.length ?? 0) === 0 ? (
              <EmptyState title="No content items" description="Create content or trigger AI automation." />
            ) : (
              <div className="space-y-2">
                {(contentQuery.data ?? []).map((item) => (
                  <div key={item.id} className="rounded-md border border-slate-200 p-3">
                    <div className="flex items-center justify-between">
                      <div className="font-medium text-slate-900">{item.title || "Untitled content"}</div>
                      <div className="text-xs text-slate-500">{item.status}</div>
                    </div>
                    <div className="mt-1 line-clamp-3 text-sm text-slate-600">{item.body}</div>
                    {(() => {
                      const quality = (item.metadata_json?.quality as Record<string, unknown> | undefined) ?? undefined;
                      if (!quality) return null;
                      return (
                        <div className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-700">
                          Risk: {String(quality.risk_score ?? "n/a")} | Flags:{" "}
                          {Array.isArray(quality.risk_flags) ? quality.risk_flags.join(", ") : "none"}
                        </div>
                      );
                    })()}
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        type="button"
                        className="px-3 py-1 text-xs"
                        disabled={reviewMutation.isPending || item.status === "approved"}
                        onClick={() => reviewMutation.mutate({ contentId: item.id, action: "approve" })}
                      >
                        Approve
                      </Button>
                      <Button
                        type="button"
                        className="bg-slate-700 px-3 py-1 text-xs hover:bg-slate-600"
                        disabled={reviewMutation.isPending || item.status === "rejected"}
                        onClick={() => reviewMutation.mutate({ contentId: item.id, action: "reject" })}
                      >
                        Reject
                      </Button>
                      <Input
                        className="max-w-64"
                        type="datetime-local"
                        value={scheduleAt}
                        onChange={(event) => setScheduleAt(event.target.value)}
                      />
                      <Button
                        type="button"
                        className="bg-emerald-600 px-3 py-1 text-xs hover:bg-emerald-500"
                        disabled={!scheduleAt || scheduleMutation.isPending}
                        onClick={() => scheduleMutation.mutate({ contentId: item.id, publishAt: new Date(scheduleAt).toISOString() })}
                      >
                        Schedule
                      </Button>
                      <Button
                        type="button"
                        className="bg-amber-600 px-3 py-1 text-xs hover:bg-amber-500"
                        disabled={qualityMutation.isPending}
                        onClick={() => qualityMutation.mutate(item.id)}
                      >
                        Evaluate quality
                      </Button>
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
