from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://crawler:crawler@localhost:5432/crawler"

    # این بخش را اضافه یا اصلاح کن:
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"  # این یعنی اگر در .env چیزی بود که اینجا تعریف نشده، ارور نده
    )

settings = Settings()
