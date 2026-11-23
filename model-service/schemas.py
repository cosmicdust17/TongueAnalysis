from pydantic import BaseModel, ConfigDict, Field

class TongueFeature(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)

class ModelResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: str = '1.0'
    model_version: str = Field(min_length=1, max_length=100)
    is_demo: bool = False
    tongue_features: list[TongueFeature] = Field(max_length=30)
    fusion_result: dict = Field(default_factory=dict)
