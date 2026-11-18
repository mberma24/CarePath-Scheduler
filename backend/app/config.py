from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "sqlite:///./kpass_scheduler.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    slot_minutes: int = 15
    schedule_horizon_days: int = 7
    clinic_timezone: str = "America/New_York"
    clinic_open_hour: int = 7  # appointments only between these hours (clinic time)
    clinic_close_hour: int = 19


settings = Settings()
