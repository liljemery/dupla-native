from pydantic import BaseModel, Field


class ModuleResponse(BaseModel):
    id: int = Field(..., description="Internal module id; not exposed to end users in UI")
    name: str

    model_config = {"from_attributes": True}
