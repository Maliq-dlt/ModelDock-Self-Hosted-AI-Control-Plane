from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "ModelDock"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    database_url: str = "postgresql+asyncpg://modeldock:modeldock@db:5432/modeldock"
    redis_url: str = "redis://redis:6379/0"
    admin_api_key: str = "change-me"
    admin_session_secret: str = ""
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    api_key_hash_secret: str = ""
    credential_encryption_key: str = ""
    request_timeout_seconds: float = 60.0
    max_retries_per_provider: int = 1
    rate_limit_per_minute: int = 60
    max_request_body_bytes: int = 1_048_576
    log_payloads: bool = False
    request_retention_days: int = 30
    otel_exporter_otlp_endpoint: str = ""
    cors_origins: str = "http://localhost:3000"

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
