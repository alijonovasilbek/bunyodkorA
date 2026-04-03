from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SystemSettingsRead(BaseModel):
    id: int
    key: str
    value: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SystemSettingsCreate(BaseModel):
    key: str
    value: Optional[str] = None
    description: Optional[str] = None


class SystemSettingsUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None
