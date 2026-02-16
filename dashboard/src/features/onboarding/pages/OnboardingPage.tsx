import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { useOnboardingStatus } from "@/features/onboarding/hooks/useOnboardingStatus";
import { createCheckoutSession } from "@/shared/api/billingApi";
import { createWebsiteChannel } from "@/shared/api/channelsApi";
import { createPostFromTemplate, publishNow, schedulePost } from "@/shared/api/postsApi";
import { createProject } from "@/shared/api/projectsApi";
import { createCampaign, createTemplate, listTemplates } from "@/shared/api/automationApi";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Input } from "@/shared/components/ui/Input";
import { Spinner } from "@/shared/components/ui/Spinner";

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function OnboardingPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { tenantId, setTenant, tenantContext } = useTenant();
  const {
    recommendedStep,
    isComplete,
    hasResourceData,
    projectsQuery,
    progressPercent,
    completeOnboarding,
    skipForNow,
    resumeOnboarding,
  } = useOnboardingStatus();

  const [searchParams, setSearchParams] = useSearchParams();
  const selectedPlan = searchParams.get("plan");
  const stepFromQuery = Number(searchParams.get("step") ?? "0");
  const step = useMemo(() => {
    if (stepFromQuery >= 1 && stepFromQuery <= 4) {
      return stepFromQuery;
    }
    return Math.min(recommendedStep, 4);
  }, [stepFromQuery, recommendedStep]);

  const [tenantInput, setTenantInput] = useState(tenantId);
  const [projectName, setProjectName] = useState("");
  const [projectIdDraft, setProjectIdDraft] = useState("");
  const [channelName, setChannelName] = useState("Website");
  const [postTitle, setPostTitle] = useState("");
  const [postAction, setPostAction] = useState<"save_draft" | "schedule" | "publish_now">("save_draft");
  const [postScheduledAt, setPostScheduledAt] = useState("");
  const [tone, setTone] = useState("professional");
  const [missingEndpointNote, setMissingEndpointNote] = useState<string | null>(null);
  const [autocreateAttempted, setAutocreateAttempted] = useState(false);

  const currentProjectId = useMemo(
    () => projectIdDraft || projectsQuery.data?.items?.[0]?.id || "",
    [projectIdDraft, projectsQuery.data?.items]
  );
  const templatesQuery = useQuery({
    queryKey: ["templates", tenantId, currentProjectId],
    queryFn: () => listTemplates(currentProjectId),
    enabled: Boolean(tenantId && currentProjectId),
  });

  useEffect(() => {
    if (stepFromQuery !== step) {
      setSearchParams({ step: String(step) }, { replace: true });
    }
  }, [stepFromQuery, step, setSearchParams]);

  useEffect(() => {
    setProjectIdDraft("");
  }, [tenantId]);

  useEffect(() => {
    if (isComplete) {
      completeOnboarding();
      navigate("/app", { replace: true });
    }
  }, [isComplete, completeOnboarding, navigate]);

  const setStep = (nextStep: number) => {
    setSearchParams({ step: String(nextStep) });
  };

  const onSkip = () => {
    skipForNow();
    navigate("/app");
  };

  const projectMutation = useMutation({
    mutationFn: () => createProject(projectName.trim(), tenantId),
    onSuccess: async (result) => {
      if (result.backendMissing) {
        setMissingEndpointNote("Backend endpoint /projects unavailable. Using local mock storage.");
      }
      setProjectIdDraft(result.item.id);
      try {
        await createCampaign({
          project_id: result.item.id,
          name: "Default campaign",
          description: "Autocreated during onboarding",
          brand_profile_json: { voice: "professional", cta: "Book a demo" },
        });
        await createTemplate({
          project_id: result.item.id,
          name: "Default post template",
          template_type: "post_text",
          prompt_template: "Napisz post o {{topic}} dla {{brand.voice}} i dodaj CTA {{offer}}.",
          output_schema_json: {
            type: "object",
            required: ["title", "body", "hashtags", "cta", "channels", "risk_flags"],
          },
        });
      } catch {
        // Optional bootstrap assets can fail when endpoints are not available.
      }
      queryClient.invalidateQueries({ queryKey: ["projects", tenantId] });
      setProjectName("");
      setStep(3);
    },
  });

  useEffect(() => {
    if (!tenantId || step !== 2 || projectMutation.isPending || autocreateAttempted) {
      return;
    }
    const hasProjects = (projectsQuery.data?.items.length ?? 0) > 0;
    if (hasProjects) {
      return;
    }
    const defaultName = tenantContext?.tenant_name ? `${tenantContext.tenant_name} Workspace` : "My first project";
    setProjectName(defaultName);
    setAutocreateAttempted(true);
    projectMutation.mutate();
  }, [
    tenantId,
    step,
    projectMutation,
    autocreateAttempted,
    projectsQuery.data?.items.length,
    tenantContext?.tenant_name,
  ]);

  const channelMutation = useMutation({
    mutationFn: () =>
      createWebsiteChannel(currentProjectId, tenantId, channelName.trim() || "Website"),
    onSuccess: (result) => {
      if (result.backendMissing) {
        setMissingEndpointNote("Backend endpoint /channels unavailable. Using local mock storage.");
      }
      queryClient.invalidateQueries({ queryKey: ["channels", tenantId] });
      setStep(4);
    },
  });

  const postMutation = useMutation({
    mutationFn: async () => {
      const selectedTemplate = templatesQuery.data?.[0];
      const created = await createPostFromTemplate(
        {
          project_id: currentProjectId,
          template_id: selectedTemplate?.id ?? "",
          title: postTitle.trim() || undefined,
          variables: {
            project_name: projectsQuery.data?.items?.find((item) => item.id === currentProjectId)?.name ?? "project",
            topic: postTitle.trim() || "new offer",
            offer: "Book a demo",
            cta: "Try now",
            tone,
          },
          status: postAction === "schedule" ? "scheduled" : "draft",
          publish_at:
            postAction === "schedule"
              ? postScheduledAt
                ? new Date(postScheduledAt).toISOString()
                : new Date().toISOString()
              : undefined,
        },
        tenantId
      );

      if (postAction === "publish_now") {
        const published = await publishNow(created.item.id, tenantId);
        return { created, published, scheduled: null };
      }

      if (postAction === "schedule") {
        const scheduleAt = postScheduledAt ? new Date(postScheduledAt).toISOString() : new Date().toISOString();
        const scheduled = await schedulePost(created.item.id, scheduleAt, tenantId);
        return { created, published: null, scheduled };
      }

      return { created, published: null, scheduled: null };
    },
    onSuccess: (result) => {
      if (result.created.backendMissing || result.scheduled?.backendMissing || result.published?.backendMissing) {
        setMissingEndpointNote("Backend endpoint /posts unavailable. Using local mock storage.");
      }
      queryClient.invalidateQueries({ queryKey: ["posts", tenantId] });
      completeOnboarding();
      navigate("/app", { replace: true });
    },
  });

  const checkoutMutation = useMutation({
    mutationFn: () => createCheckoutSession(selectedPlan || "Pro"),
    onSuccess: (payload) => {
      if (payload.checkout_url) {
        window.location.assign(payload.checkout_url);
      } else {
        pushToast("Checkout not available for this environment.", "error");
      }
    },
    onError: () => pushToast("Failed to start checkout", "error"),
  });

  const steps = ["Tenant", "Project", "Channel", "Post"];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Onboarding"
        description="Skonfiguruj tenant i utworz pierwsze zasoby, aby szybciej osiagnac first value."
        actions={
          <div className="flex items-center gap-2">
            {selectedPlan ? (
              <Button type="button" onClick={() => checkoutMutation.mutate()} disabled={checkoutMutation.isPending}>
                {checkoutMutation.isPending ? "Redirecting..." : `Activate ${selectedPlan}`}
              </Button>
            ) : null}
            <Button type="button" className="bg-slate-700 hover:bg-slate-600" onClick={onSkip}>
              Skip for now
            </Button>
          </div>
        }
      />

      {!hasResourceData ? (
        <Card>
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <Spinner /> Loading onboarding context...
          </div>
        </Card>
      ) : null}

      <Card>
        <div className="mb-4">
          <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
            <span>Progress</span>
            <span>{progressPercent}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-slate-200">
            <div className="h-full rounded-full bg-brand-700 transition-all" style={{ width: `${progressPercent}%` }} />
          </div>
        </div>
        <div className="mb-4 grid grid-cols-4 gap-2">
          {steps.map((label, index) => {
            const currentStep = index + 1;
            const active = step === currentStep;
            const done = step > currentStep;
            return (
              <button
                key={label}
                type="button"
                onClick={() => setStep(currentStep)}
                className={`rounded-md border px-3 py-2 text-left text-sm ${
                  active
                    ? "border-brand-700 bg-brand-50 text-brand-900"
                    : done
                      ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                      : "border-slate-200 bg-white text-slate-500"
                }`}
              >
                <div className="font-semibold">Step {currentStep}</div>
                <div>{label}</div>
              </button>
            );
          })}
        </div>

        {missingEndpointNote ? (
          <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
            {missingEndpointNote}
          </div>
        ) : null}

        {step === 1 ? (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">Set tenant context for scoped API calls.</p>
            {tenantContext?.current_tenant_id || tenantContext?.tenant_id ? (
              <Button
                type="button"
                className="bg-slate-800 hover:bg-slate-700"
                onClick={() => {
                  const resolved = tenantContext.current_tenant_id ?? tenantContext.tenant_id;
                  if (resolved) {
                    setTenant(resolved);
                    setTenantInput(resolved);
                    resumeOnboarding();
                    setStep(2);
                  }
                }}
              >
                Use current ({(tenantContext.current_tenant_id ?? tenantContext.tenant_id)?.slice(0, 8)})
              </Button>
            ) : null}
            <Input value={tenantInput} onChange={(event) => setTenantInput(event.target.value)} placeholder="Tenant UUID" />
            <div className="flex justify-end">
              <Button
                type="button"
                onClick={() => {
                  if (!uuidPattern.test(tenantInput)) {
                    pushToast("Invalid tenant UUID", "error");
                    return;
                  }
                  setTenant(tenantInput);
                  resumeOnboarding();
                  setStep(2);
                }}
              >
                Confirm tenant
              </Button>
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-4">
            <Input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Project name" />
            <div className="flex justify-between">
              <Button type="button" className="bg-slate-600 hover:bg-slate-500" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button
                type="button"
                disabled={!tenantId || !projectName.trim() || projectMutation.isPending}
                onClick={() => projectMutation.mutate()}
              >
                {projectMutation.isPending ? "Creating..." : "Create first project"}
              </Button>
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="space-y-4">
            <div className="rounded-md border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-900">
              Suggested first channel: <span className="font-semibold">LinkedIn or Website</span>. Start with Website for fastest first value.
            </div>
            <Input
              value={channelName}
              onChange={(event) => setChannelName(event.target.value)}
              placeholder="Website channel name"
            />
            <div className="flex justify-between">
              <Button type="button" className="bg-slate-600 hover:bg-slate-500" onClick={() => setStep(2)}>
                Back
              </Button>
              <Button
                type="button"
                disabled={!tenantId || !currentProjectId}
                onClick={() => channelMutation.mutate()}
              >
                {channelMutation.isPending ? "Connecting..." : "Connect first channel"}
              </Button>
            </div>
          </div>
        ) : null}

        {step === 4 ? (
          <div className="space-y-4">
            <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
              One step away from publishing. Generate your first post and choose publish now or schedule.
            </div>
            <Input value={postTitle} onChange={(event) => setPostTitle(event.target.value)} placeholder="Post title" />
            <div className="grid gap-3 md:grid-cols-2">
              <Input value={tone} onChange={(event) => setTone(event.target.value)} placeholder="Brand tone (e.g. confident)" />
              <select
                value={postAction}
                onChange={(event) => {
                  const next = event.target.value as typeof postAction;
                  setPostAction(next);
                }}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="save_draft">Save draft</option>
                <option value="schedule">Schedule</option>
                <option value="publish_now">Publish now</option>
              </select>
              <Input
                type="datetime-local"
                value={postScheduledAt}
                onChange={(event) => setPostScheduledAt(event.target.value)}
                disabled={postAction !== "schedule"}
              />
            </div>
            <div className="flex justify-between">
              <Button type="button" className="bg-slate-600 hover:bg-slate-500" onClick={() => setStep(3)}>
                Back
              </Button>
              <Button
                type="button"
                disabled={!tenantId || !postTitle.trim() || !templatesQuery.data?.[0]?.id || postMutation.isPending}
                onClick={() => postMutation.mutate()}
              >
                {postMutation.isPending
                  ? "Processing..."
                  : postAction === "publish_now"
                    ? "Generate and publish"
                    : postAction === "schedule"
                      ? "Generate and schedule"
                      : "Generate first draft"}
              </Button>
            </div>
          </div>
        ) : null}
      </Card>

      {!tenantId ? (
        <EmptyState
          title="Tenant is required"
          description="Set tenant context in step 1 to continue onboarding."
          actionLabel="Go to step 1"
          onAction={() => setStep(1)}
        />
      ) : null}
    </div>
  );
}
