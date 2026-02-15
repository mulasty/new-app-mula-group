import { api } from "@/shared/api/client";
import { isEndpointMissing } from "@/shared/api/errors";
import { addMockItem, getMockCollection } from "@/shared/api/mockStore";
import { runtimeConfig } from "@/shared/config/runtime";
import { ApiListEnvelope, Channel, CreateResult, ListResult } from "@/shared/api/types";

type CreateChannelPayload = {
  project_id: string;
  type: "website";
  name?: string;
};

export async function listChannels(tenantId: string, projectId?: string): Promise<ListResult<Channel>> {
  try {
    const params = projectId ? { project_id: projectId } : undefined;
    const response = await api.get<Channel[] | ApiListEnvelope<Channel>>("/channels", { params });
    const items = Array.isArray(response.data) ? response.data : response.data.items;
    return { items, source: "api", backendMissing: false };
  } catch (error) {
    // TODO: remove mock fallback when backend GET /channels is available.
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const allChannels = getMockCollection<Channel>(tenantId, "channels");
      return {
        items: projectId ? allChannels.filter((row) => row.project_id === projectId) : allChannels,
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}

export async function createChannel(
  payload: CreateChannelPayload,
  tenantId: string
): Promise<CreateResult<Channel>> {
  try {
    const response = await api.post<Channel>("/channels", payload);
    return { item: response.data, source: "api", backendMissing: false };
  } catch (error) {
    // TODO: remove mock fallback when backend POST /channels is available.
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const item: Channel = {
        id: crypto.randomUUID(),
        company_id: tenantId,
        project_id: payload.project_id,
        type: payload.type,
        name: payload.name ?? "Website",
        status: "active",
        created_at: new Date().toISOString(),
      };
      return {
        item: addMockItem(tenantId, "channels", item),
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}

export async function createWebsiteChannel(
  projectId: string,
  tenantId: string,
  name?: string
): Promise<CreateResult<Channel>> {
  return createChannel(
    {
      project_id: projectId,
      type: "website",
      name,
    },
    tenantId
  );
}
