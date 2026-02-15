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
  };
};

export type MeResponse = {
  id: string;
  company_id: string;
  email: string;
  role?: string;
};

export type TenantContextResponse = {
  tenant_id?: string | null;
  current_tenant_id?: string | null;
  tenants?: Array<{ id: string; name?: string }>;
};

export type Project = {
  id: string;
  company_id: string;
  name: string;
  created_at?: string;
};

export type ChannelType = "website" | "linkedin" | "facebook" | "instagram" | "youtube";
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
