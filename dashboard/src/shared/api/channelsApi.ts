import { api } from "@/shared/api/client";
import { isEndpointMissing } from "@/shared/api/errors";
import { addMockItem, getMockCollection } from "@/shared/api/mockStore";
import { runtimeConfig } from "@/shared/config/runtime";
import { Channel, CreateResult, ListResult } from "@/shared/api/types";

type CreateChannelPayload = {
  type: Channel["type"];
  credentials_json: string;
};

export async function listChannels(tenantId: string): Promise<ListResult<Channel>> {
  try {
    const response = await api.get<Channel[]>("/channels");
    return { items: response.data, source: "api", backendMissing: false };
  } catch (error) {
    // TODO: remove mock fallback when backend GET /channels is available.
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      return {
        items: getMockCollection<Channel>(tenantId, "channels"),
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
        type: payload.type,
        credentials_json: payload.credentials_json,
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
