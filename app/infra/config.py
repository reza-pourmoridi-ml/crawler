from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://crawler:crawler@localhost:5432/crawler"
    storage_root: str = "storage"
    learn_interval_seconds: int = 7 * 24 * 60 * 60
    learn_retry_seconds: int = 60 * 60
    learn_job_timeout: int = 6 * 60 * 60
    extractor_job_timeout: int = 300
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:14b"
    ollama_timeout: int = 360
    final_validation_max_html_chars: int = 100000

    # این بخش را اضافه یا اصلاح کن:
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"  # این یعنی اگر در .env چیزی بود که اینجا تعریف نشده، ارور نده
    )

settings = Settings()
