from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "sqlite:///./kpass_scheduler.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    slot_minutes: int = Field(default=15, ge=1, le=60)
    schedule_horizon_days: int = Field(default=7, ge=1)
    clinic_timezone: str = "America/New_York"
    # Appointments only between these whole hours (clinic time); 24 means midnight
    clinic_open_hour: int = Field(default=7, ge=0, le=23)
    clinic_close_hour: int = Field(default=19, ge=1, le=24)

    @model_validator(mode="after")
    def check_scheduling_settings(self) -> Self:
        """Fail at startup with a clear message instead of misbehaving on the first search."""
        if 60 % self.slot_minutes != 0:
            raise ValueError(
                f"SLOT_MINUTES must divide an hour evenly (e.g. 5, 10, 15, 30), "
                f"got {self.slot_minutes}"
            )
        if self.clinic_open_hour >= self.clinic_close_hour:
            raise ValueError(
                f"CLINIC_OPEN_HOUR ({self.clinic_open_hour}) must be before "
                f"CLINIC_CLOSE_HOUR ({self.clinic_close_hour})"
            )
        try:
            ZoneInfo(self.clinic_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"Unknown CLINIC_TIMEZONE: {self.clinic_timezone!r}") from None
        return self


settings = Settings()
