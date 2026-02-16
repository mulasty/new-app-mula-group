import { api } from "@/shared/api/client";
import { BrandProfile } from "@/shared/api/types";

type BrandProfilePayload = {
  project_id?: string | null;
  brand_name: string;
  language: string;
  tone: string;
  target_audience?: string | null;
  do_list: string[];
  dont_list: string[];
  forbidden_claims: string[];
  preferred_hashtags: string[];
  compliance_notes?: string | null;
};

export async function listBrandProfiles(projectId?: string): Promise<BrandProfile[]> {
  const response = await api.get<{ items: BrandProfile[] }>("/brand-profiles", {
    params: projectId ? { project_id: projectId } : {},
  });
  return response.data.items ?? [];
}

export async function createBrandProfile(payload: BrandProfilePayload): Promise<BrandProfile> {
  const response = await api.post<BrandProfile>("/brand-profiles", payload);
  return response.data;
}

export async function patchBrandProfile(profileId: string, payload: Partial<BrandProfilePayload>): Promise<BrandProfile> {
  const response = await api.patch<BrandProfile>(`/brand-profiles/${profileId}`, payload);
  return response.data;
}

export async function deleteBrandProfile(profileId: string): Promise<void> {
  await api.delete(`/brand-profiles/${profileId}`);
}
