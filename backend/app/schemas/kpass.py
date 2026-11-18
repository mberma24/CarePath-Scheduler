from typing import Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.config import settings

MAX_STEP_MINUTES = 24 * 60


class KPassStepBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(gt=0, le=MAX_STEP_MINUTES, multiple_of=settings.slot_minutes)
    # Set at most one: a specific resource, or any resource of a type. Neither = rest step.
    resource_id: int | None = None
    resource_type: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def check_one_resource_kind(self) -> Self:
        if self.resource_id is not None and self.resource_type is not None:
            raise ValueError("Set resource_id or resource_type, not both")
        return self


class KPassStepCreate(KPassStepBase):
    position: int | None = Field(default=None, ge=0)  # None or past the end = append


class KPassStepUpdate(KPassStepBase):
    pass


class KPassStepRead(KPassStepBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int


class KPassStepOrder(BaseModel):
    step_ids: list[int]


class KPassBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)


class KPassCreate(KPassBase):
    pass


class KPassUpdate(KPassBase):
    pass


class KPassRead(KPassBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    steps: list[KPassStepRead]

    @computed_field
    @property
    def total_minutes(self) -> int:
        return sum(step.duration_minutes for step in self.steps)
