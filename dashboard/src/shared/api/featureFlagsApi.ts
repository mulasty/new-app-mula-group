import { api } from "@/shared/api/client";
import { FeatureFlagItem } from "@/shared/api/types";

export async function listFeatureFlags(): Promise<FeatureFlagItem[]> {
  const response = await api.get<{ items: FeatureFlagItem[] }>("/feature-flags");
  return response.data.items ?? [];
}

export async function patchFeatureFlag(
  id: string,
  payload: { enabled_globally?: boolean; enabled_for_tenant?: boolean }
): Promise<FeatureFlagItem> {
  const response = await api.patch<{ item: FeatureFlagItem }>(`/feature-flags/${id}`, payload);
  return response.data.item;
}
