from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "sqlite:///./kpass_scheduler.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    slot_minutes: int = 15
    schedule_horizon_days: int = 1
    clinic_timezone: str = "America/New_York"


settings = Settings()
