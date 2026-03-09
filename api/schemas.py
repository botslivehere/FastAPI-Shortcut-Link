from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class UserAuth(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)

class LinkCreate(BaseModel):
    original_url: str
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None
    project: Optional[str] = None

class LinkUpdate(BaseModel):
    new_original_url: str

class LinkOut(BaseModel):
    model_config = {"from_attributes": True}
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    project: Optional[str] = None
    clicks_count: int