from datetime import datetime

from pydantic import BaseModel


class PresidentDocumentRead(BaseModel):
    id: int
    name: str
    description: str
    image_urls: list[str]
    document_url: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
