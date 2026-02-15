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

export type Channel = {
  id: string;
  company_id: string;
  type: "website" | "facebook" | "instagram" | "youtube";
  credentials_json: string;
  created_at?: string;
};

export type PostItem = {
  id: string;
  company_id: string;
  title: string;
  content: string;
  status: "draft" | "scheduled" | "published";
  scheduled_at?: string;
  created_at?: string;
};
