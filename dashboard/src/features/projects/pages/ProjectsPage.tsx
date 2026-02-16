import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";

import { useTenant } from "@/app/providers/TenantProvider";
import { useToast } from "@/app/providers/ToastProvider";
import { createCheckoutSession } from "@/shared/api/billingApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { createProject, listProjects } from "@/shared/api/projectsApi";
import { EmptyState } from "@/shared/components/EmptyState";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { Input } from "@/shared/components/ui/Input";

export function ProjectsPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { tenantId } = useTenant();
  const [name, setName] = useState("");
  const [planLimitHit, setPlanLimitHit] = useState(false);

  const projectsQuery = useQuery({
    queryKey: ["projects", tenantId],
    queryFn: () => listProjects(tenantId),
    enabled: Boolean(tenantId),
  });

  const createMutation = useMutation({
    mutationFn: (projectName: string) => createProject(projectName, tenantId),
    onSuccess: (created) => {
      queryClient.setQueryData(["projects", tenantId], (current: { items?: unknown[]; source?: string } | undefined) => ({
        items: [created.item, ...(current?.items ?? [])],
        source: created.source,
        backendMissing: created.backendMissing,
      }));
      setName("");
    },
    onError: (error) => {
      const axiosError = error as AxiosError<{ error_code?: string }>;
      setPlanLimitHit(axiosError.response?.data?.error_code === "PLAN_LIMIT_EXCEEDED");
      pushToast(getApiErrorMessage(error, "Failed to create project"), "error");
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Projects" description="Manage tenant projects and content workspaces." />

      {!tenantId ? (
        <EmptyState
          title="Tenant is required"
          description="Set tenant context before creating projects."
          actionLabel="Open onboarding"
          onAction={() => navigate("/app/onboarding?step=1")}
        />
      ) : (
        <>
          <Card title="Create project">
            {planLimitHit ? (
              <div className="mb-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                Plan limit exceeded. Upgrade plan to create more projects.
                <button
                  type="button"
                  className="ml-2 underline"
                  onClick={async () => {
                    try {
                      const checkout = await createCheckoutSession("Pro");
                      if (checkout.checkout_url) {
                        window.location.assign(checkout.checkout_url);
                      }
                    } catch {
                      // toast handled by API client
                    }
                  }}
                >
                  Upgrade now
                </button>
              </div>
            ) : null}
            <div className="flex gap-2">
              <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Project name" />
              <Button
                type="button"
                disabled={!name.trim() || createMutation.isPending}
                onClick={() => createMutation.mutate(name.trim())}
              >
                {createMutation.isPending ? "Creating..." : "Create"}
              </Button>
            </div>
          </Card>

          {projectsQuery.data?.backendMissing ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              Backend endpoint missing. Showing mock data stored locally.
            </div>
          ) : null}

          <Card title="Project list">
            <ul className="space-y-2 text-sm text-slate-700">
              {(projectsQuery.data?.items ?? []).map((project) => (
                <li key={project.id} className="rounded-md border border-slate-200 px-3 py-2">
                  {project.name}
                </li>
              ))}
            </ul>
            {(projectsQuery.data?.items.length ?? 0) === 0 ? (
              <EmptyState
                title="No projects yet"
                description="Create your first project to continue onboarding."
                actionLabel="Open onboarding"
                onAction={() => navigate("/app/onboarding?step=2")}
              />
            ) : null}
          </Card>
        </>
      )}
    </div>
  );
}
