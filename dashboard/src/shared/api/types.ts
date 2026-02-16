export type DataSource = "api" | "mock";

export type ListResult<T> = {
  items: T[];
  source: DataSource;
  backendMissing: boolean;
};

export type CreateResult<T> = {
  item: T;
  source: DataSource;
  backendMissing: boolean;
};

export type ApiListEnvelope<T> = {
  items: T[];
};

export type TokenResponse = {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  user?: {
    id: string;
    company_id: string;
    email: string;
    role?: string;
    is_platform_admin?: boolean;
  };
};

export type MeResponse = {
  id: string;
  company_id: string;
  email: string;
  role?: string;
  is_platform_admin?: boolean;
};

export type TenantContextResponse = {
  tenant_id?: string | null;
  current_tenant_id?: string | null;
  tenant_name?: string | null;
  tenants?: Array<{ id: string; name?: string }>;
};

export type Project = {
  id: string;
  company_id: string;
  name: string;
  created_at?: string;
};

export type ChannelType =
  | "website"
  | "linkedin"
  | "facebook"
  | "instagram"
  | "tiktok"
  | "threads"
  | "x"
  | "pinterest"
  | "youtube";
export type ChannelStatus = "active" | "disabled";
export type ChannelCapabilities = {
  text?: boolean;
  image?: boolean;
  video?: boolean;
  reels?: boolean;
  shorts?: boolean;
  max_length?: number;
};

export type Channel = {
  id: string;
  company_id: string;
  project_id: string;
  type: ChannelType;
  name?: string;
  status?: ChannelStatus;
  capabilities_json?: ChannelCapabilities;
  credentials_json?: string;
  created_at?: string;
  updated_at?: string;
};

export type MetaConnectionPage = {
  id: string;
  page_id: string;
  page_name: string;
  created_at: string;
};

export type MetaConnectionInstagramAccount = {
  id: string;
  instagram_account_id: string;
  username?: string | null;
  linked_page_id?: string | null;
  created_at: string;
};

export type MetaConnectionsResponse = {
  facebook_pages: MetaConnectionPage[];
  instagram_accounts: MetaConnectionInstagramAccount[];
};

export type PostStatus = "draft" | "scheduled" | "publishing" | "published" | "published_partial" | "failed";

export type PostItem = {
  id: string;
  company_id: string;
  project_id: string;
  title: string;
  content: string;
  status: PostStatus;
  publish_at?: string | null;
  scheduled_at?: string | null;
  last_error?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type PublishEvent = {
  id: string;
  company_id: string;
  project_id: string;
  post_id: string;
  channel_id?: string | null;
  event_type: string;
  status: "ok" | "error";
  attempt: number;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type WebsitePublication = {
  id: string;
  company_id: string;
  project_id: string;
  post_id: string;
  slug: string;
  title: string;
  content: string;
  published_at: string;
  created_at: string;
};

export type PublishingSummary = {
  scheduled: number;
  publishing: number;
  published: number;
  failed: number;
  success_rate: number;
  avg_publish_time_sec: number;
};

export type PublishingTimeRange = "7d" | "30d" | "90d";

export type PublishingTimeseriesPoint = {
  date: string;
  published: number;
  failed: number;
};

export type ActivityStreamItem = {
  timestamp: string;
  post_id: string;
  event_type: string;
  status: "ok" | "error";
  metadata: Record<string, unknown>;
};

export type ConnectorAvailability = {
  platform: string;
  display_name: string;
  capabilities: ChannelCapabilities;
  oauth_start_path?: string;
  available: boolean;
};

export type CampaignStatus = "draft" | "active" | "paused" | "archived";

export type Campaign = {
  id: string;
  company_id: string;
  project_id: string;
  name: string;
  description?: string | null;
  status: CampaignStatus;
  timezone: string;
  language: string;
  brand_profile_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AutomationTriggerType = "cron" | "interval" | "event";
export type AutomationActionType = "generate_post" | "schedule_post" | "publish_now" | "sync_metrics";

export type AutomationRule = {
  id: string;
  company_id: string;
  project_id: string;
  campaign_id?: string | null;
  name: string;
  is_enabled: boolean;
  trigger_type: AutomationTriggerType;
  trigger_config_json: Record<string, unknown>;
  action_type: AutomationActionType;
  action_config_json: Record<string, unknown>;
  guardrails_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ContentTemplate = {
  id: string;
  company_id: string;
  project_id: string;
  name: string;
  category?: "product launch" | "educational" | "social proof" | "engagement" | "promotional" | string;
  tone?: string;
  content_structure?: string;
  template_type: "post_text" | "carousel_plan" | "video_script";
  prompt_template: string;
  output_schema_json: Record<string, unknown>;
  default_values_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ContentItemStatus =
  | "draft"
  | "needs_review"
  | "approved"
  | "rejected"
  | "scheduled"
  | "published"
  | "failed";

export type ContentItem = {
  id: string;
  company_id: string;
  project_id: string;
  campaign_id?: string | null;
  template_id?: string | null;
  status: ContentItemStatus;
  title?: string | null;
  body: string;
  metadata_json: Record<string, unknown>;
  source: "ai" | "manual";
  created_at: string;
  updated_at: string;
};

export type AutomationRunStatus = "queued" | "running" | "success" | "partial" | "failed";

export type AutomationRun = {
  id: string;
  company_id: string;
  project_id: string;
  rule_id: string;
  status: AutomationRunStatus;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
  stats_json: Record<string, unknown>;
  created_at: string;
};

export type AutomationEventItem = {
  id: string;
  company_id: string;
  project_id: string;
  run_id: string;
  event_type: string;
  status: "ok" | "error";
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type CalendarPayload = {
  posts: Array<{
    id: string;
    project_id: string;
    title: string;
    status: string;
    publish_at?: string | null;
  }>;
  content_items: Array<{
    id: string;
    project_id: string;
    title?: string | null;
    status: string;
    created_at: string;
    scheduled_for?: string | null;
  }>;
};

export type FeatureFlagItem = {
  id: string;
  key: string;
  description?: string | null;
  enabled_globally: boolean;
  enabled_for_tenant: boolean;
  effective_enabled: boolean;
  updated_at: string;
};

export type BillingPlan = {
  id: string;
  name: string;
  monthly_price: number;
  max_projects: number;
  max_posts_per_month: number;
  max_connectors: number;
};

export type BillingSnapshot = {
  subscription: {
    id: string;
    status: string;
    current_period_end?: string | null;
    stripe_customer_id?: string | null;
    stripe_subscription_id?: string | null;
  };
  plan: BillingPlan;
  usage: {
    posts_used_current_period: number;
    projects_count?: number;
    connectors_count?: number;
    posts_usage_percent?: number;
    projects_usage_percent?: number;
    connectors_usage_percent?: number;
  };
  lifecycle?: {
    in_grace_period: boolean;
    expired: boolean;
    days_left_in_period: number;
  };
};

export type BillingEventItem = {
  id: string;
  event_type: string;
  message: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type AdminTenantItem = {
  company_id: string;
  name: string;
  slug: string;
  subscription_status: string;
  posts_used_current_period: number;
  published_posts: number;
};

export type AdminAuditLogItem = {
  id: string;
  company_id: string;
  action: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type PlatformIncidentItem = {
  id: string;
  company_id?: string | null;
  incident_type: string;
  severity: string;
  status: string;
  message: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
  resolved_at?: string | null;
};

export type AdminSystemOverview = {
  system_health_score: number;
  components: Array<{
    component: string;
    status: string;
    latency_ms: number;
    error_rate: number;
    updated_at: string;
  }>;
  worker_queue_depth: number;
  tenant_risk_ranking: Array<{
    company_id: string;
    risk_score: number;
    risk_level: string;
  }>;
  revenue: {
    tenant_count: number;
    total_mrr: number;
    avg_churn_risk_score: number;
  };
  active_incidents: PlatformIncidentItem[];
};
