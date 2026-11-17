from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class BlockBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    start_time: AwareDatetime  # must include a UTC offset, e.g. "2026-11-18T09:00:00-05:00"
    end_time: AwareDatetime
    reason: str | None = Field(default=None, max_length=200)

    @field_validator("start_time", "end_time")
    @classmethod
    def convert_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def check_end_after_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class BlockCreate(BlockBase):
    patient_id: int | None = None
    resource_id: int | None = None

    @model_validator(mode="after")
    def check_exactly_one_owner(self):
        if (self.patient_id is None) == (self.resource_id is None):
            raise ValueError("Provide exactly one of patient_id or resource_id")
        return self


class BlockUpdate(BlockBase):
    pass  # Times and reason only; a block can't move to a different owner.


class BlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int | None
    resource_id: int | None
    start_time: datetime
    end_time: datetime
    reason: str | None

    @field_validator("start_time", "end_time")
    @classmethod
    def assume_utc(cls, value: datetime) -> datetime:
        # SQLite drops the offset, so naive values coming back from the DB are UTC.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
