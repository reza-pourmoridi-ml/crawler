from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://crawler:crawler@localhost:5432/crawler"
    storage_root: str = "storage"
    learn_max_new_templates: int = Field(default=20, ge=1)
    learn_max_templates: int = Field(default=250, ge=1)
    learn_job_timeout: int = 6 * 60 * 60
    extractor_job_timeout: int = 300
    scrape_job_timeout: int = Field(default=15 * 60, ge=1)
    pending_job_timeout: int = Field(default=24 * 60 * 60, ge=1)
    cleanup_interval_seconds: int = Field(default=60 * 60, ge=1)
    artifact_retention_seconds: int = Field(default=7 * 24 * 60 * 60, ge=1)
    job_retention_seconds: int = Field(default=7 * 24 * 60 * 60, ge=1)
    temporary_retention_seconds: int = Field(default=24 * 60 * 60, ge=1)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:3b"
    ollama_timeout: int = 360
    final_validation_max_html_chars: int = 100000
    auth_state_file: str = "storage/auth/auth.json"
    control_host: str = "0.0.0.0"
    control_port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

settings = Settings()
