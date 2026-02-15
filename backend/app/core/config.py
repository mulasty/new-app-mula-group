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

    jwt_secret_key: str = "change_this_in_production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_minutes: int = 10080
    token_encryption_key: str | None = None

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
