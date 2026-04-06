from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.permissions import (
    PERM_REPORTS_ATTENDANCE_VIEW,
    PERM_REPORTS_DASHBOARD_VIEW,
)
from app.deps import require_permission
from app.models.attendance import Attendance, Session
from app.models.domain import Group, Student
from app.models.enums import AttendanceStatus, GroupStatus, StudentStatus
from app.schemas.common import DataResponse
from app.schemas.report import (
    DashboardSummary,
    GroupAttendanceReport,
    StudentAttendanceReport,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get(
    "/dashboard/summary",
    response_model=DataResponse[DashboardSummary],
    dependencies=[Depends(require_permission(PERM_REPORTS_DASHBOARD_VIEW))],
)
async def get_dashboard_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    today = date.today()

    active_students = (
        await db.execute(
            select(func.count(Student.id)).where(Student.status == StudentStatus.ACTIVE)
        )
    ).scalar() or 0

    active_groups = (
        await db.execute(
            select(func.count(Group.id)).where(Group.status == GroupStatus.ACTIVE)
        )
    ).scalar() or 0

    today_sessions = (
        await db.execute(
            select(func.count(Session.id)).where(Session.session_date == today)
        )
    ).scalar() or 0

    today_attendances = (
        await db.execute(
            select(func.count(Attendance.id))
            .join(Session, Attendance.session_id == Session.id)
            .where(Session.session_date == today)
        )
    ).scalar() or 0

    return DataResponse(
        data=DashboardSummary(
            active_students=active_students,
            active_groups=active_groups,
            today_sessions=today_sessions,
            today_attendances=today_attendances,
        )
    )


@router.get(
    "/attendance/groups",
    response_model=DataResponse[list[GroupAttendanceReport]],
    dependencies=[Depends(require_permission(PERM_REPORTS_ATTENDANCE_VIEW))],
)
async def get_group_attendance_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    group_id: Optional[int] = Query(None),
):
    groups_query = select(Group).where(Group.status != GroupStatus.DELETED)
    if group_id:
        groups_query = groups_query.where(Group.id == group_id)

    groups_result = await db.execute(groups_query.order_by(Group.name))
    groups = groups_result.scalars().all()

    reports: list[GroupAttendanceReport] = []
    for group in groups:
        session_conditions = [Session.group_id == group.id]
        attendance_conditions = [Session.group_id == group.id]
        if from_date:
            session_conditions.append(Session.session_date >= from_date)
            attendance_conditions.append(Session.session_date >= from_date)
        if to_date:
            session_conditions.append(Session.session_date <= to_date)
            attendance_conditions.append(Session.session_date <= to_date)

        session_query = select(func.count(Session.id)).where(and_(*session_conditions))
        attendance_query = (
            select(
                func.count(Attendance.id),
                func.sum(
                    case(
                        (Attendance.status == AttendanceStatus.PRESENT, 1),
                        else_=0,
                    )
                ),
            )
            .select_from(Attendance)
            .join(Session, Attendance.session_id == Session.id)
            .where(and_(*attendance_conditions))
        )

        total_sessions = (await db.execute(session_query)).scalar() or 0
        attendance_row = (await db.execute(attendance_query)).one()
        total_attendance_rows = attendance_row[0] or 0
        present_count = attendance_row[1] or 0

        total_students = (
            await db.execute(
                select(func.count(Student.id)).where(
                    Student.group_id == group.id,
                    Student.status == StudentStatus.ACTIVE,
                )
            )
        ).scalar() or 0

        attendance_percentage = 0.0
        if total_attendance_rows:
            attendance_percentage = round((present_count / total_attendance_rows) * 100, 2)

        reports.append(
            GroupAttendanceReport(
                group_id=group.id,
                group_name=group.name,
                total_sessions=total_sessions,
                total_students=total_students,
                attendance_percentage=attendance_percentage,
            )
        )

    return DataResponse(data=reports)


@router.get(
    "/attendance/students/{student_id}",
    response_model=DataResponse[StudentAttendanceReport],
    dependencies=[Depends(require_permission(PERM_REPORTS_ATTENDANCE_VIEW))],
)
async def get_student_attendance_report(
    student_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
):
    student_result = await db.execute(select(Student).where(Student.id == student_id))
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    query = (
        select(Attendance.status, func.count(Attendance.id))
        .join(Session, Attendance.session_id == Session.id)
        .where(Attendance.student_id == student_id)
        .group_by(Attendance.status)
    )

    conditions = []
    if from_date:
        conditions.append(Session.session_date >= from_date)
    if to_date:
        conditions.append(Session.session_date <= to_date)
    if conditions:
        query = query.where(and_(*conditions))

    stats_result = await db.execute(query)
    rows = stats_result.all()
    counts = {status: count for status, count in rows}

    present_count = counts.get(AttendanceStatus.PRESENT, 0)
    absent_count = counts.get(AttendanceStatus.ABSENT, 0)
    late_count = counts.get(AttendanceStatus.LATE, 0)
    total_sessions = present_count + absent_count + late_count
    attendance_percentage = round((present_count / total_sessions) * 100, 2) if total_sessions else 0.0

    return DataResponse(
        data=StudentAttendanceReport(
            student_id=student.id,
            student_name=f"{student.first_name} {student.last_name}",
            total_sessions=total_sessions,
            present_count=present_count,
            absent_count=absent_count,
            late_count=late_count,
            attendance_percentage=attendance_percentage,
        )
    )
