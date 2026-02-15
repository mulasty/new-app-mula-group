import { api } from "@/shared/api/client";
import { isEndpointMissing } from "@/shared/api/errors";
import { addMockItem, getMockCollection } from "@/shared/api/mockStore";
import { runtimeConfig } from "@/shared/config/runtime";
import { CreateResult, ListResult, PostItem } from "@/shared/api/types";

type CreatePostPayload = {
  title: string;
  content: string;
  status: PostItem["status"];
  scheduled_at?: string;
};

export async function listPosts(tenantId: string): Promise<ListResult<PostItem>> {
  try {
    const response = await api.get<PostItem[]>("/posts");
    return { items: response.data, source: "api", backendMissing: false };
  } catch (error) {
    // TODO: remove mock fallback when backend GET /posts is available.
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      return {
        items: getMockCollection<PostItem>(tenantId, "posts"),
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}

export async function createPost(payload: CreatePostPayload, tenantId: string): Promise<CreateResult<PostItem>> {
  try {
    const response = await api.post<PostItem>("/posts", payload);
    return { item: response.data, source: "api", backendMissing: false };
  } catch (error) {
    // TODO: remove mock fallback when backend POST /posts is available.
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const item: PostItem = {
        id: crypto.randomUUID(),
        company_id: tenantId,
        title: payload.title,
        content: payload.content,
        status: payload.status,
        scheduled_at: payload.scheduled_at,
        created_at: new Date().toISOString(),
      };
      return {
        item: addMockItem(tenantId, "posts", item),
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}
