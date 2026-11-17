from pydantic import BaseModel, ConfigDict, Field


class ResourceBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=50)


class ResourceCreate(ResourceBase):
    pass


class ResourceUpdate(ResourceBase):
    pass


class ResourceRead(ResourceBase):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int
