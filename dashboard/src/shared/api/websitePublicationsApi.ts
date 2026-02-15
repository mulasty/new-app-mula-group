import { api } from "@/shared/api/client";
import { isEndpointMissing } from "@/shared/api/errors";
import { getMockCollection } from "@/shared/api/mockStore";
import { runtimeConfig } from "@/shared/config/runtime";
import {
  ApiListEnvelope,
  ListResult,
  PostItem,
  WebsitePublication,
} from "@/shared/api/types";

export async function listWebsitePublications(
  tenantId: string,
  projectId?: string
): Promise<ListResult<WebsitePublication>> {
  try {
    const params = projectId ? { project_id: projectId } : undefined;
    const response = await api.get<WebsitePublication[] | ApiListEnvelope<WebsitePublication>>(
      "/website/publications",
      { params }
    );
    const items = Array.isArray(response.data) ? response.data : response.data.items;
    return { items, source: "api", backendMissing: false };
  } catch (error) {
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const mockPosts = getMockCollection<PostItem>(tenantId, "posts");
      const published = mockPosts.filter((post) => post.status === "published");
      const filtered = projectId ? published.filter((post) => post.project_id === projectId) : published;
      const items: WebsitePublication[] = filtered.map((post) => ({
        id: post.id,
        company_id: post.company_id,
        project_id: post.project_id,
        post_id: post.id,
        slug: `${post.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${post.id.slice(0, 8)}`,
        title: post.title,
        content: post.content,
        published_at: post.publish_at ?? post.updated_at ?? post.created_at ?? new Date().toISOString(),
        created_at: post.created_at ?? new Date().toISOString(),
      }));

      return { items, source: "mock", backendMissing: true };
    }
    throw error;
  }
}
