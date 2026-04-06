from pydantic import BaseModel


class DashboardSummary(BaseModel):
    active_students: int
    active_groups: int
    today_sessions: int
    today_attendances: int


class GroupAttendanceReport(BaseModel):
    group_id: int
    group_name: str
    total_sessions: int
    total_students: int
    attendance_percentage: float


class StudentAttendanceReport(BaseModel):
    student_id: int
    student_name: str
    total_sessions: int
    present_count: int
    absent_count: int
    late_count: int
    attendance_percentage: float
