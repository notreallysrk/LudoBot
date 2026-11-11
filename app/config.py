from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    bot_token: str
    mongodb_uri: str
    mongodb_db: str = "ludo_arena"
    webhook_base_url: str | None = None
    webhook_secret: str | None = None
    port: int = 8080
    environment: str = "production"
    log_level: str = "INFO"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
