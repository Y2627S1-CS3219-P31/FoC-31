# AI-INFLUENCED: CI lint fixes applied with Codex; see ai/usage-log.md.
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class SupplierDetails(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True
    )
    
    id: str
    name: str
    category: str
    building: str
    floor: str | None = None
    location_description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    starting_time: str | None = None
    closing_time: str | None = None
    image_url: str | None = None
    active: bool
