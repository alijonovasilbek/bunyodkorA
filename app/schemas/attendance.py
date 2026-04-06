from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import AttendanceStatus


class SessionRead(BaseModel):
    id: int
    session_date: date
    topic: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    station: Optional[str] = None
    description: Optional[str] = None
    konspekt_url: Optional[str] = None
    group_id: int
    created_by_user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    """Head Coach creates session with basic info only (no description/konspekt)"""
    session_date: date
    topic: Optional[str] = None
    start_time: Optional[str] = None
    description: Optional[str] = None
    end_time: Optional[str] = None
    station: Optional[str] = None
    group_id: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_date": "2026-03-05",
                "topic": "Yugurish mashqlari",
                "start_time": "10:00",
                "end_time": "12:00",
                "station": "Stadion 1",
                "description": "Bugungi mashg'ulot rejasi",
                "group_id": 1,
            }
        }
    )


class BulkSessionCreate(BaseModel):
    """Create multiple sessions in one request"""
    sessions: list[SessionCreate] = Field(default_factory=list)


class SessionUpdate(BaseModel):
    """Update session with konspekt upload (konspekt is mandatory)"""
    description: Optional[str] = None
    konspekt_url: str  # Mandatory - coach must upload konspekt


class SessionWithAttendances(SessionRead):
    """Session with attendance records"""
    attendances: list["AttendanceRead"] = []


class AttendanceRead(BaseModel):
    id: int
    status: AttendanceStatus
    comment: Optional[str] = None
    session_id: int
    student_id: int
    marked_by_user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AttendanceCreate(BaseModel):
    student_id: int
    status: AttendanceStatus
    comment: Optional[str] = None


class BulkAttendanceCreate(BaseModel):
    """Create multiple attendance records for a session"""
    session_id: int
    attendances: list[AttendanceCreate]


class AttendanceStats(BaseModel):
    """Attendance statistics for a student or group"""
    total_sessions: int
    present_count: int
    absent_count: int
    late_count: int
    attendance_rate: float  # Percentage of present sessions


class GateLogRead(BaseModel):
    id: int
    allowed: bool
    reason: Optional[str] = None
    gate_timestamp: datetime
    student_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class GateCallbackRequest(BaseModel):
    student_id: Optional[int] = None
    face_id: Optional[str] = None


class GateCallbackResponse(BaseModel):
    allowed: bool
    reason: str
    student_id: Optional[int] = None
