from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class WaitingListCreate(BaseModel):
    """Add prospective student to waiting list with full information"""
    # Student information
    student_first_name: str = Field(min_length=1, max_length=100, description="Student first name")
    student_last_name: str = Field(min_length=1, max_length=100, description="Student last name")
    birth_year: int = Field(ge=2000, le=2030, description="Student birth year (e.g., 2015, 2020)")

    # Parent information
    father_name: Optional[str] = Field(default=None, max_length=200, description="Father's full name")
    father_phone: Optional[str] = Field(default=None, max_length=20, description="Father's phone number")
    mother_name: Optional[str] = Field(default=None, max_length=200, description="Mother's full name")
    mother_phone: Optional[str] = Field(default=None, max_length=20, description="Mother's phone number")

    # Group and metadata
    group_id: int = Field(description="Group ID to join")
    priority: int = Field(default=0, ge=0, le=100, description="Priority in queue (higher = earlier)")
    notes: Optional[str] = Field(default=None, description="Additional notes")


class WaitingListUpdate(BaseModel):
    """Update waiting list entry"""
    student_first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    student_last_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    birth_year: Optional[int] = Field(default=None, ge=2000, le=2030)
    father_name: Optional[str] = Field(default=None, max_length=200)
    father_phone: Optional[str] = Field(default=None, max_length=20)
    mother_name: Optional[str] = Field(default=None, max_length=200)
    mother_phone: Optional[str] = Field(default=None, max_length=20)
    priority: Optional[int] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = None


class WaitingListRead(BaseModel):
    """Waiting list entry with all information"""
    id: int
    student_first_name: str
    student_last_name: str
    birth_year: int
    father_name: Optional[str] = None
    father_phone: Optional[str] = None
    mother_name: Optional[str] = None
    mother_phone: Optional[str] = None
    group_id: int
    priority: int
    notes: Optional[str] = None
    added_by_user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
