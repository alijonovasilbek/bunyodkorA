"""Reserved router for future shared upload endpoints."""
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/uploads", tags=["Uploads"])


class UploadResponse(BaseModel):
    """Response after successful file upload"""
    url: str
    filename: str
    message: str


class MultipleUploadResponse(BaseModel):
    """Response after successful multiple file uploads"""
    urls: List[str]
    count: int
    message: str
