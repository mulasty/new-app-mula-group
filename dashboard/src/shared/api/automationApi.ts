import { api } from "@/shared/api/client";
import {
  AutomationEventItem,
  AutomationRule,
  AutomationRun,
  CalendarPayload,
  Campaign,
  ContentItem,
  ContentTemplate,
} from "@/shared/api/types";

type ListEnvelope<T> = { items: T[] };

export async function listCampaigns(projectId?: string): Promise<Campaign[]> {
  const response = await api.get<ListEnvelope<Campaign>>("/campaigns", {
    params: projectId ? { project_id: projectId } : undefined,
  });
  return response.data.items ?? [];
}

export async function createCampaign(payload: {
  project_id: string;
  name: string;
  description?: string;
  timezone?: string;
  language?: string;
  brand_profile_json?: Record<string, unknown>;
}): Promise<Campaign> {
  const response = await api.post<Campaign>("/campaigns", payload);
  return response.data;
}

export async function activateCampaign(id: string): Promise<Campaign> {
  const response = await api.post<Campaign>(`/campaigns/${id}/activate`);
  return response.data;
}

export async function pauseCampaign(id: string): Promise<Campaign> {
  const response = await api.post<Campaign>(`/campaigns/${id}/pause`);
  return response.data;
}

export async function listTemplates(projectId?: string): Promise<ContentTemplate[]> {
  const response = await api.get<ListEnvelope<ContentTemplate>>("/templates", {
    params: projectId ? { project_id: projectId } : undefined,
  });
  return response.data.items ?? [];
}

export async function createTemplate(payload: {
  project_id: string;
  name: string;
  category?: "product launch" | "educational" | "social proof" | "engagement" | "promotional" | string;
  tone?: string;
  content_structure?: string;
  template_type: "post_text" | "carousel_plan" | "video_script";
  prompt_template: string;
  output_schema_json?: Record<string, unknown>;
  default_values_json?: Record<string, unknown>;
}): Promise<ContentTemplate> {
  const response = await api.post<ContentTemplate>("/templates", payload);
  return response.data;
}

export async function listRules(projectId?: string, campaignId?: string): Promise<AutomationRule[]> {
  const response = await api.get<ListEnvelope<AutomationRule>>("/automation/rules", {
    params: {
      ...(projectId ? { project_id: projectId } : {}),
      ...(campaignId ? { campaign_id: campaignId } : {}),
    },
  });
  return response.data.items ?? [];
}

export async function createRule(payload: {
  project_id: string;
  campaign_id?: string;
  name: string;
  is_enabled?: boolean;
  trigger_type: "cron" | "interval" | "event";
  trigger_config_json?: Record<string, unknown>;
  action_type: "generate_post" | "schedule_post" | "publish_now" | "sync_metrics";
  action_config_json?: Record<string, unknown>;
  guardrails_json?: Record<string, unknown>;
}): Promise<AutomationRule> {
  const response = await api.post<AutomationRule>("/automation/rules", payload);
  return response.data;
}

export async function runRuleNow(ruleId: string): Promise<{ run_id: string; status: string }> {
  const response = await api.post<{ run_id: string; status: string }>(`/automation/rules/${ruleId}/run-now`);
  return response.data;
}

export async function listRuns(projectId?: string, ruleId?: string): Promise<AutomationRun[]> {
  const response = await api.get<ListEnvelope<AutomationRun>>("/automation/runs", {
    params: {
      ...(projectId ? { project_id: projectId } : {}),
      ...(ruleId ? { rule_id: ruleId } : {}),
    },
  });
  return response.data.items ?? [];
}

export async function listRunEvents(runId: string): Promise<AutomationEventItem[]> {
  const response = await api.get<ListEnvelope<AutomationEventItem>>(`/automation/runs/${runId}/events`);
  return response.data.items ?? [];
}

export async function listContent(projectId?: string, statusFilter?: string): Promise<ContentItem[]> {
  const response = await api.get<ListEnvelope<ContentItem>>("/content", {
    params: {
      ...(projectId ? { project_id: projectId } : {}),
      ...(statusFilter ? { status: statusFilter } : {}),
    },
  });
  return response.data.items ?? [];
}

export async function createContent(payload: {
  project_id: string;
  campaign_id?: string;
  template_id?: string;
  title?: string;
  body: string;
  metadata_json?: Record<string, unknown>;
  status?: string;
}): Promise<ContentItem> {
  const response = await api.post<ContentItem>("/content", payload);
  return response.data;
}

export async function approveContent(contentId: string, comment?: string): Promise<ContentItem> {
  const response = await api.post<ContentItem>(`/content/${contentId}/approve`, { comment });
  return response.data;
}

export async function rejectContent(contentId: string, comment?: string): Promise<ContentItem> {
  const response = await api.post<ContentItem>(`/content/${contentId}/reject`, { comment });
  return response.data;
}

export async function scheduleContent(contentId: string, publishAt: string): Promise<{ content_item: ContentItem; post_id: string }> {
  const response = await api.post<{ content_item: ContentItem; post_id: string }>(`/content/${contentId}/schedule`, {
    publish_at: publishAt,
  });
  return response.data;
}

export async function getCalendar(projectId: string, from: string, to: string): Promise<CalendarPayload> {
  const response = await api.get<CalendarPayload>("/calendar", {
    params: { project_id: projectId, from, to },
  });
  return response.data;
}
