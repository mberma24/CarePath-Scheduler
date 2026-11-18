from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator


class ScheduleRequest(BaseModel):
    kpass_id: int
    patient_id: int
    start: AwareDatetime | None = None  # default: now
    end: AwareDatetime | None = None  # default: end of today (clinic time)

    @model_validator(mode="after")
    def check_end_after_start(self):
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class BookRequest(BaseModel):
    kpass_id: int
    patient_id: int
    start: AwareDatetime  # usually the start_time returned by POST /schedule


class ScheduledStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step_id: int
    name: str
    resource_id: int | None
    start_time: datetime
    end_time: datetime


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    found: bool
    start_time: datetime | None = None
    end_time: datetime | None = None
    steps: list[ScheduledStepRead] = []
