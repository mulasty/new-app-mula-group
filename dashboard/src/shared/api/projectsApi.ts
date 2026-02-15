import { api } from "@/shared/api/client";
import { isEndpointMissing } from "@/shared/api/errors";
import { addMockItem, getMockCollection } from "@/shared/api/mockStore";
import { runtimeConfig } from "@/shared/config/runtime";
import { ApiListEnvelope, CreateResult, ListResult, Project } from "@/shared/api/types";

export async function listProjects(tenantId: string): Promise<ListResult<Project>> {
  try {
    const response = await api.get<Project[] | ApiListEnvelope<Project>>("/projects");
    const items = Array.isArray(response.data) ? response.data : response.data.items;
    return { items, source: "api", backendMissing: false };
  } catch (error) {
    // TODO: remove mock fallback when backend GET /projects is guaranteed in all environments.
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      return {
        items: getMockCollection<Project>(tenantId, "projects"),
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}

export async function createProject(name: string, tenantId: string): Promise<CreateResult<Project>> {
  try {
    const response = await api.post<Project>("/projects", { name });
    return { item: response.data, source: "api", backendMissing: false };
  } catch (error) {
    // TODO: remove mock fallback when backend POST /projects is guaranteed in all environments.
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const item: Project = {
        id: crypto.randomUUID(),
        company_id: tenantId,
        name,
        created_at: new Date().toISOString(),
      };
      return {
        item: addMockItem(tenantId, "projects", item),
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}
