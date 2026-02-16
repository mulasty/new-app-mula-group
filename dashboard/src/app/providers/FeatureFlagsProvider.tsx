import { createContext, useContext, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { useTenant } from "@/app/providers/TenantProvider";
import { listFeatureFlags } from "@/shared/api/featureFlagsApi";
import { FeatureFlagItem } from "@/shared/api/types";

type FeatureFlagsContextValue = {
  flags: FeatureFlagItem[];
  isLoading: boolean;
  isEnabled: (key: string) => boolean;
};

const FeatureFlagsContext = createContext<FeatureFlagsContextValue>({
  flags: [],
  isLoading: false,
  isEnabled: () => false,
});

export function FeatureFlagsProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const { tenantId } = useTenant();
  const query = useQuery({
    queryKey: ["featureFlags", tenantId],
    queryFn: () => listFeatureFlags(),
    enabled: Boolean(tenantId),
    staleTime: 30000,
  });

  const value = useMemo<FeatureFlagsContextValue>(() => {
    const flags = query.data ?? [];
    const map = new Map(flags.map((flag) => [flag.key, flag.effective_enabled]));
    return {
      flags,
      isLoading: query.isLoading,
      isEnabled: (key: string) => Boolean(map.get(key)),
    };
  }, [query.data, query.isLoading]);

  return <FeatureFlagsContext.Provider value={value}>{children}</FeatureFlagsContext.Provider>;
}

export function useFeatureFlags(): FeatureFlagsContextValue {
  return useContext(FeatureFlagsContext);
}
