import { api } from "@/shared/api/client";
import { isEndpointMissing } from "@/shared/api/errors";
import { addMockItem, getMockCollection, updateMockItem } from "@/shared/api/mockStore";
import { runtimeConfig } from "@/shared/config/runtime";
import {
  ApiListEnvelope,
  CreateResult,
  ListResult,
  PostItem,
  PostQualityReport,
  PostStatus,
  PublishEvent,
} from "@/shared/api/types";

type CreatePostPayload = {
  project_id: string;
  title: string;
  content: string;
  status?: PostStatus;
};

type CreatePostFromTemplatePayload = {
  project_id: string;
  template_id: string;
  variables?: Record<string, string>;
  title?: string;
  status?: "draft" | "scheduled";
  publish_at?: string;
};

type UpdatePostPayload = {
  title?: string;
  content?: string;
  status?: PostStatus;
  publish_at?: string | null;
};

type TimelineListResult = ListResult<PublishEvent>;

const MOCK_TIMELINE_PREFIX = "cc_mock_post_timeline";

function getTimelineStorageKey(tenantId: string, postId: string): string {
  return `${MOCK_TIMELINE_PREFIX}_${tenantId}_${postId}`;
}

function readMockTimeline(tenantId: string, postId: string): PublishEvent[] {
  try {
    const raw = localStorage.getItem(getTimelineStorageKey(tenantId, postId));
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as PublishEvent[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function appendMockTimelineEvent(tenantId: string, event: PublishEvent): void {
  const current = readMockTimeline(tenantId, event.post_id);
  const next = [event, ...current];
  localStorage.setItem(getTimelineStorageKey(tenantId, event.post_id), JSON.stringify(next));
}

function normalizePost(post: PostItem): PostItem {
  if (post.publish_at == null && post.scheduled_at != null) {
    return { ...post, publish_at: post.scheduled_at };
  }
  return post;
}

function nowIso(): string {
  return new Date().toISOString();
}

export async function listPosts(
  tenantId: string,
  projectId?: string,
  status?: PostStatus
): Promise<ListResult<PostItem>> {
  try {
    const params = {
      ...(projectId ? { project_id: projectId } : {}),
      ...(status ? { status } : {}),
    };
    const response = await api.get<PostItem[] | ApiListEnvelope<PostItem>>("/posts", { params });
    const items = (Array.isArray(response.data) ? response.data : response.data.items).map(normalizePost);
    return { items, source: "api", backendMissing: false };
  } catch (error) {
    // TODO: remove mock fallback when backend GET /posts is available.
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const allPosts = getMockCollection<PostItem>(tenantId, "posts").map(normalizePost);
      const filteredByProject = projectId ? allPosts.filter((row) => row.project_id === projectId) : allPosts;
      const filtered = status ? filteredByProject.filter((row) => row.status === status) : filteredByProject;
      return {
        items: filtered,
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
    return { item: normalizePost(response.data), source: "api", backendMissing: false };
  } catch (error) {
    // TODO: remove mock fallback when backend POST /posts is available.
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const item: PostItem = {
        id: crypto.randomUUID(),
        company_id: tenantId,
        project_id: payload.project_id,
        title: payload.title,
        content: payload.content,
        status: payload.status ?? "draft",
        publish_at: null,
        created_at: nowIso(),
        updated_at: nowIso(),
      };
      return {
        item: addMockItem(tenantId, "posts", item as PostItem),
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}

export async function createPostFromTemplate(
  payload: CreatePostFromTemplatePayload,
  tenantId: string
): Promise<CreateResult<PostItem>> {
  try {
    const response = await api.post<PostItem>("/posts/from-template", payload);
    return { item: normalizePost(response.data), source: "api", backendMissing: false };
  } catch (error) {
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const item: PostItem = {
        id: crypto.randomUUID(),
        company_id: tenantId,
        project_id: payload.project_id,
        title: payload.title ?? "Template post",
        content: `Generated from template ${payload.template_id}`,
        status: payload.status ?? "draft",
        publish_at: payload.publish_at ?? null,
        created_at: nowIso(),
        updated_at: nowIso(),
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

export async function updatePost(
  postId: string,
  payload: UpdatePostPayload,
  tenantId: string
): Promise<CreateResult<PostItem>> {
  try {
    const response = await api.patch<PostItem>(`/posts/${postId}`, payload);
    return { item: normalizePost(response.data), source: "api", backendMissing: false };
  } catch (error) {
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const next = updateMockItem<PostItem>(tenantId, "posts", postId, (current) => ({
        ...current,
        ...payload,
        updated_at: nowIso(),
      }));
      if (!next) {
        throw error;
      }
      return {
        item: normalizePost(next),
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}

export async function schedulePost(
  postId: string,
  publishAt: string,
  tenantId: string
): Promise<CreateResult<PostItem>> {
  try {
    const response = await api.post<PostItem>(`/posts/${postId}/schedule`, { publish_at: publishAt });
    return { item: normalizePost(response.data), source: "api", backendMissing: false };
  } catch (error) {
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const next = updateMockItem<PostItem>(tenantId, "posts", postId, (current) => ({
        ...current,
        status: "scheduled",
        publish_at: publishAt,
        last_error: null,
        updated_at: nowIso(),
      }));

      if (!next) {
        throw error;
      }

      appendMockTimelineEvent(tenantId, {
        id: crypto.randomUUID(),
        company_id: next.company_id,
        project_id: next.project_id,
        post_id: next.id,
        channel_id: null,
        event_type: "PostScheduled",
        status: "ok",
        attempt: 1,
        metadata_json: { publish_at: publishAt },
        created_at: nowIso(),
      });

      return {
        item: normalizePost(next),
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}

export async function publishNow(postId: string, tenantId: string): Promise<CreateResult<PostItem>> {
  try {
    const response = await api.post<PostItem>(`/posts/${postId}/publish-now`);
    return { item: normalizePost(response.data), source: "api", backendMissing: false };
  } catch (error) {
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      const next = updateMockItem<PostItem>(tenantId, "posts", postId, (current) => ({
        ...current,
        status: "published",
        publish_at: nowIso(),
        last_error: null,
        updated_at: nowIso(),
      }));

      if (!next) {
        throw error;
      }

      appendMockTimelineEvent(tenantId, {
        id: crypto.randomUUID(),
        company_id: next.company_id,
        project_id: next.project_id,
        post_id: next.id,
        channel_id: null,
        event_type: "PostPublished",
        status: "ok",
        attempt: 1,
        metadata_json: {},
        created_at: nowIso(),
      });

      return {
        item: normalizePost(next),
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}

export async function getTimeline(postId: string, tenantId: string): Promise<TimelineListResult> {
  try {
    const response = await api.get<PublishEvent[] | ApiListEnvelope<PublishEvent>>(`/posts/${postId}/timeline`);
    const items = Array.isArray(response.data) ? response.data : response.data.items;
    return { items, source: "api", backendMissing: false };
  } catch (error) {
    if (runtimeConfig.featureFlags.enableMockFallback && isEndpointMissing(error)) {
      return {
        items: readMockTimeline(tenantId, postId),
        source: "mock",
        backendMissing: true,
      };
    }
    throw error;
  }
}

export async function runPostQualityCheck(
  postId: string,
  _tenantId: string,
  payload?: { brand_profile_id?: string; recent_posts_window?: number }
): Promise<{
  post_id: string;
  score: number;
  risk_level: "low" | "medium" | "high";
  issues: Array<{ code: string; message: string; severity: "info" | "warn" | "block"; suggestion: string }>;
  recommendations: string[];
  status: PostStatus;
  created_at: string;
}> {
  const response = await api.post(`/posts/${postId}/quality-check`, payload ?? {});
  return response.data;
}

export async function getPostQualityReport(postId: string, _tenantId: string): Promise<{ post_id: string; report: PostQualityReport | null }> {
  const response = await api.get<{ post_id: string; report: PostQualityReport | null }>(`/posts/${postId}/quality-report`);
  return response.data;
}

export async function approvePost(postId: string, _tenantId: string): Promise<CreateResult<PostItem>> {
  const response = await api.post<PostItem>(`/posts/${postId}/approve`);
  return { item: normalizePost(response.data), source: "api", backendMissing: false };
}

export async function rejectPost(
  postId: string,
  reason: string,
  _tenantId: string
): Promise<CreateResult<PostItem>> {
  const response = await api.post<PostItem>(`/posts/${postId}/reject`, { reason });
  return { item: normalizePost(response.data), source: "api", backendMissing: false };
}
