from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.config import settings

MAX_STEP_MINUTES = 24 * 60


class KPassStepBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(gt=0, le=MAX_STEP_MINUTES, multiple_of=settings.slot_minutes)
    resource_id: int | None = None  # None = rest step


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
