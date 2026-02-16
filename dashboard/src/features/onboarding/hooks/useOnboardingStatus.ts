import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { useTenant } from "@/app/providers/TenantProvider";
import { listChannels } from "@/shared/api/channelsApi";
import { listPosts } from "@/shared/api/postsApi";
import { listProjects } from "@/shared/api/projectsApi";
import { getOnboardingState, setOnboardingState } from "@/shared/utils/storage";

type OnboardingProgress = {
  skipped: boolean;
  completed: boolean;
};

export function useOnboardingStatus() {
  const { tenantId, isContextKnown } = useTenant();
  const [progress, setProgress] = useState<OnboardingProgress>(getOnboardingState(tenantId));

  useEffect(() => {
    setProgress(getOnboardingState(tenantId));
  }, [tenantId]);

  const canInspectResources = Boolean(tenantId) && isContextKnown;

  const projectsQuery = useQuery({
    queryKey: ["projects", tenantId],
    queryFn: () => listProjects(tenantId),
    enabled: canInspectResources,
  });

  const channelsQuery = useQuery({
    queryKey: ["channels", tenantId],
    queryFn: () => listChannels(tenantId),
    enabled: canInspectResources,
  });

  const postsQuery = useQuery({
    queryKey: ["posts", tenantId],
    queryFn: () => listPosts(tenantId),
    enabled: canInspectResources,
  });

  const recommendedStep = useMemo(() => {
    if (!tenantId || !isContextKnown) {
      return 1;
    }

    if ((projectsQuery.data?.items.length ?? 0) === 0) {
      return 2;
    }

    if ((channelsQuery.data?.items.length ?? 0) === 0) {
      return 3;
    }

    if ((postsQuery.data?.items.length ?? 0) === 0) {
      return 4;
    }

    return 5;
  }, [
    tenantId,
    isContextKnown,
    projectsQuery.data?.items.length,
    channelsQuery.data?.items.length,
    postsQuery.data?.items.length,
  ]);

  const hasResourceData = !canInspectResources || (!projectsQuery.isLoading && !channelsQuery.isLoading && !postsQuery.isLoading);
  const isComplete = progress.completed || recommendedStep === 5;
  const isOnboardingRequired = !isComplete;
  const showSoftReminder = progress.skipped && isOnboardingRequired;

  const updateProgress = (next: OnboardingProgress) => {
    setOnboardingState(next, tenantId);
    setProgress(next);
  };

  const completeOnboarding = () => updateProgress({ skipped: false, completed: true });
  const skipForNow = () => updateProgress({ skipped: true, completed: false });
  const resumeOnboarding = () => updateProgress({ skipped: false, completed: false });

  return {
    tenantId,
    recommendedStep,
    isComplete,
    isOnboardingRequired,
    showSoftReminder,
    hasResourceData,
    projectsQuery,
    channelsQuery,
    postsQuery,
    progressPercent: Math.min(100, Math.max(0, (recommendedStep - 1) * 25)),
    completeOnboarding,
    skipForNow,
    resumeOnboarding,
  };
}
