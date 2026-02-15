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

export type ChannelType = "website" | "facebook" | "instagram" | "youtube";
export type ChannelStatus = "active" | "disabled";

export type Channel = {
  id: string;
  company_id: string;
  project_id: string;
  type: ChannelType;
  name?: string;
  status?: ChannelStatus;
  credentials_json?: string;
  created_at?: string;
  updated_at?: string;
};

export type PostStatus = "draft" | "scheduled" | "publishing" | "published" | "failed";

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
