from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Control Center"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "control_center"
    postgres_user: str = "control_center"
    postgres_password: str = "control_center"

    redis_host: str = "localhost"
    redis_port: int = 6379

    database_url: str | None = None
    redis_url: str | None = None
    frontend_origin: str = "http://localhost:3000"
    additional_frontend_origins: str = ""
    tenant_rate_limit_per_minute: int = 120
    worker_heartbeat_key: str = "worker:heartbeat"
    worker_heartbeat_ttl_seconds: int = 45

    jwt_secret_key: str = "change_this_in_production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_minutes: int = 10080
    token_encryption_key: str | None = None
    auth_use_httponly_cookies: bool = False
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "strict"
    auth_cookie_domain: str | None = None

    stripe_api_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_checkout_success_url: str = "http://localhost:3000/app/onboarding?checkout=success"
    stripe_checkout_cancel_url: str = "http://localhost:3000/pricing?checkout=cancelled"
    stripe_price_id_starter: str | None = None
    stripe_price_id_pro: str | None = None
    stripe_price_id_enterprise: str | None = None
    feature_flag_cache_ttl_seconds: int = 60
    platform_admin_emails: str = ""

    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    linkedin_redirect_uri: str = "http://localhost:8000/channels/linkedin/oauth/callback"
    linkedin_dashboard_redirect_url: str = "http://localhost:3000/app/channels"
    linkedin_oauth_scope: str = "openid profile w_member_social"

    meta_app_id: str | None = None
    meta_app_secret: str | None = None
    meta_redirect_uri: str = "http://localhost:8000/channels/meta/oauth/callback"
    meta_dashboard_redirect_url: str = "http://localhost:3000/app/channels"
    meta_oauth_scope: str = (
        "pages_manage_posts pages_read_engagement instagram_basic instagram_content_publish"
    )
    meta_graph_api_base_url: str = "https://graph.facebook.com/v21.0"
    public_app_url: str = "http://localhost:3000"

    tiktok_client_key: str | None = None
    tiktok_client_secret: str | None = None
    tiktok_redirect_uri: str = "http://localhost:8000/channels/tiktok/oauth/callback"
    tiktok_oauth_scope: str = "user.info.basic,video.publish"

    threads_app_id: str | None = None
    threads_app_secret: str | None = None
    threads_redirect_uri: str = "http://localhost:8000/channels/threads/oauth/callback"
    threads_oauth_scope: str = "threads_basic,threads_content_publish"

    x_client_id: str | None = None
    x_client_secret: str | None = None
    x_redirect_uri: str = "http://localhost:8000/channels/x/oauth/callback"
    x_oauth_scope: str = "tweet.read tweet.write users.read offline.access"

    pinterest_client_id: str | None = None
    pinterest_client_secret: str | None = None
    pinterest_redirect_uri: str = "http://localhost:8000/channels/pinterest/oauth/callback"
    pinterest_oauth_scope: str = "pins:read,pins:write,boards:read,user_accounts:read"

    ai_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = 30.0
    openai_temperature: float = 0.2

    @property
    def platform_admin_email_list(self) -> list[str]:
        if not self.platform_admin_emails.strip():
            return []
        return [value.strip().lower() for value in self.platform_admin_emails.split(",") if value.strip()]

    @property
    def cors_allowed_origins(self) -> list[str]:
        origins = [self.frontend_origin.strip(), self.public_app_url.strip()]
        if self.additional_frontend_origins.strip():
            origins.extend(
                [value.strip() for value in self.additional_frontend_origins.split(",") if value.strip()]
            )
        unique: list[str] = []
        for origin in origins:
            if origin and origin not in unique:
                unique.append(origin)
        return unique

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cache_redis_url(self) -> str:
        if self.redis_url:
            return self.redis_url
        return f"redis://{self.redis_host}:{self.redis_port}/0"


settings = Settings()
