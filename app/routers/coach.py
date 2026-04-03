from typing import Annotated, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from app.models.enums import AttendanceStatus
from app.core.db import get_db
from app.core.permissions import PERM_ATTENDANCE_COACH_MARK
from app.models.domain import Group, Student, GroupStatus
from app.models.attendance import Session, Attendance
from app.schemas.group import GroupRead
from app.schemas.attendance import (
    SessionRead, SessionCreate, AttendanceCreate, SessionWithAttendances,
    StudentWithDebtInfo, BulkAttendanceCreate, AttendanceStats, AttendanceRead, DebtMonthInfo
)
from app.schemas.common import DataResponse
from app.deps import require_permission, CurrentUser
from app.services.debt import calculate_student_previous_months_debt
from app.services.file_upload import file_upload_service

router = APIRouter(prefix="/coach", tags=["Coach"])


@router.get("/groups", response_model=DataResponse[list[GroupRead]], dependencies=[Depends(require_permission(PERM_ATTENDANCE_COACH_MARK))])
async def get_coach_groups(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get coach's assigned groups (excluding deleted groups)"""
    result = await db.execute(
        select(Group).where(
            Group.coach_id == user.id,
            Group.status != GroupStatus.DELETED
        )
    )
    groups = result.scalars().all()
    return DataResponse(data=[GroupRead.model_validate(g) for g in groups])


@router.get("/sessions", response_model=DataResponse[list[SessionRead]], dependencies=[Depends(require_permission(PERM_ATTENDANCE_COACH_MARK))])
async def get_coach_sessions(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    date_filter: Optional[date] = Query(None, alias="date"),
    group_id: Optional[int] = Query(None),
):
    """
    Get sessions for coach's groups (excluding deleted groups).
    Coach can view sessions by date and group, and mark attendance.
    """
    session_date = date_filter or date.today()

    query = select(Session).join(Group).where(
        and_(
            Group.coach_id == user.id,
            Session.session_date == session_date,
            Group.status != GroupStatus.DELETED
        )
    )

    if group_id:
        query = query.where(Session.group_id == group_id)

    result = await db.execute(query)
    sessions = result.scalars().all()
    return DataResponse(data=[SessionRead.model_validate(s) for s in sessions])


@router.get("/sessions/{session_id}/students-with-debt-info", response_model=DataResponse[list[StudentWithDebtInfo]], dependencies=[Depends(require_permission(PERM_ATTENDANCE_COACH_MARK))])
async def get_session_students_with_debt(
    session_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    students_result = await db.execute(select(Student).where(Student.group_id == session.group_id))
    students = students_result.scalars().all()

    students_with_debt = []
    for student in students:
        debt, overdue_months = await calculate_student_previous_months_debt(db, student.id)
        has_debt = debt > 0
        overdue_month_models = [
            DebtMonthInfo(year=year, month=month, amount=amount)
            for year, month, amount in overdue_months
        ]
        debt_warning = None
        if has_debt:
            months_text = ", ".join(f"{year}-{month:02d}" for year, month, _ in overdue_months)
            debt_warning = f"Student owes {debt} UZS for months: {months_text}"

        students_with_debt.append(
            StudentWithDebtInfo(
                student_id=student.id,
                first_name=student.first_name,
                last_name=student.last_name,
                has_debt=has_debt,
                debt_amount=debt,
                debt_warning=debt_warning,
                overdue_months=overdue_month_models,
            )
        )

    return DataResponse(data=students_with_debt)


@router.post("/sessions/{session_id}/attendance", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_ATTENDANCE_COACH_MARK))])
async def mark_attendance(
    session_id: int,
    data: AttendanceCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check if attendance has already been marked for this session
    existing_attendance = await db.execute(
        select(Attendance).where(Attendance.session_id == session_id).limit(1)
    )
    if existing_attendance.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Bu dars uchun davomat allaqachon qilib bo'lingan. Bir darsga faqat bir marta davomat qilish mumkin."
        )

    student_result = await db.execute(select(Student).where(Student.id == data.student_id))
    if not student_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Student with ID {data.student_id} not found")

    attendance = Attendance(
        session_id=session_id,
        student_id=data.student_id,
        status=data.status,
        comment=data.comment,
        marked_by_user_id=user.id,
    )
    db.add(attendance)
    await db.commit()
    await db.refresh(attendance)

    return DataResponse(data={"message": "Attendance marked successfully", "attendance_id": attendance.id})




@router.get("/sessions/{session_id}", response_model=DataResponse[SessionWithAttendances], dependencies=[Depends(require_permission(PERM_ATTENDANCE_COACH_MARK))])
async def get_session_details(
    session_id: int,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get session details with all attendance records"""
    session_result = await db.execute(
        select(Session)
        .options(selectinload(Session.attendances))
        .join(Group)
        .where(Session.id == session_id, Group.coach_id == user.id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or you do not have permission to view it"
        )

    return DataResponse(data=SessionWithAttendances.model_validate(session))


@router.post("/sessions/{session_id}/bulk-attendance", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_ATTENDANCE_COACH_MARK))])
async def mark_bulk_attendance(
    session_id: int,
    data: BulkAttendanceCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Mark attendance for multiple students at once"""
    # Verify session exists and coach has access
    session_result = await db.execute(
        select(Session)
        .join(Group)
        .where(Session.id == session_id, Group.coach_id == user.id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or you do not have permission to mark attendance"
        )

    # Check if attendance has already been marked for this session
    existing_attendance = await db.execute(
        select(Attendance).where(Attendance.session_id == session_id).limit(1)
    )
    if existing_attendance.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Bu dars uchun davomat allaqachon qilib bo'lingan. Bir darsga faqat bir marta davomat qilish mumkin."
        )

    if data.session_id != session_id:
        raise HTTPException(status_code=400, detail="Session ID mismatch")

    # Create attendance records
    attendance_records = []
    for att_data in data.attendances:
        # Verify student exists
        student_result = await db.execute(select(Student).where(Student.id == att_data.student_id))
        if not student_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail=f"Student with ID {att_data.student_id} not found")

        attendance = Attendance(
            session_id=session_id,
            student_id=att_data.student_id,
            status=att_data.status,
            comment=att_data.comment,
            marked_by_user_id=user.id,
        )
        db.add(attendance)
        attendance_records.append(attendance)

    await db.commit()

    return DataResponse(data={
        "message": f"Successfully marked attendance for {len(attendance_records)} students",
        "count": len(attendance_records)
    })


@router.get("/groups/{group_id}/attendance-stats", response_model=DataResponse[AttendanceStats], dependencies=[Depends(require_permission(PERM_ATTENDANCE_COACH_MARK))])
async def get_group_attendance_stats(
    group_id: int,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
):
    """Get attendance statistics for a group"""
    # Verify group exists and coach has access
    group_result = await db.execute(
        select(Group).where(Group.id == group_id, Group.coach_id == user.id)
    )
    group = group_result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=404,
            detail="Group not found or you do not have permission to view statistics"
        )

    # Get all sessions for the group
    sessions_query = select(Session).where(Session.group_id == group_id)
    if from_date:
        sessions_query = sessions_query.where(Session.session_date >= from_date)
    if to_date:
        sessions_query = sessions_query.where(Session.session_date <= to_date)

    sessions_result = await db.execute(sessions_query)
    sessions = sessions_result.scalars().all()
    session_ids = [s.id for s in sessions]

    if not session_ids:
        return DataResponse(data=AttendanceStats(
            total_sessions=0,
            present_count=0,
            absent_count=0,
            late_count=0,
            attendance_rate=0.0
        ))

    # Count attendance by status
    present_count = await db.execute(
        select(func.count(Attendance.id)).where(
            Attendance.session_id.in_(session_ids),
            Attendance.status == AttendanceStatus.PRESENT
        )
    )
    absent_count = await db.execute(
        select(func.count(Attendance.id)).where(
            Attendance.session_id.in_(session_ids),
            Attendance.status == AttendanceStatus.ABSENT
        )
    )
    late_count = await db.execute(
        select(func.count(Attendance.id)).where(
            Attendance.session_id.in_(session_ids),
            Attendance.status == AttendanceStatus.LATE
        )
    )

    present = present_count.scalar() or 0
    absent = absent_count.scalar() or 0
    late = late_count.scalar() or 0
    total = present + absent + late

    attendance_rate = (present / total * 100) if total > 0 else 0.0

    return DataResponse(data=AttendanceStats(
        total_sessions=len(sessions),
        present_count=present,
        absent_count=absent,
        late_count=late,
        attendance_rate=round(attendance_rate, 2)
    ))


@router.get("/students/{student_id}/attendance-stats", response_model=DataResponse[AttendanceStats], dependencies=[Depends(require_permission(PERM_ATTENDANCE_COACH_MARK))])
async def get_student_attendance_stats(
    student_id: int,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
):
    """Get attendance statistics for a specific student"""
    # Verify student exists and is in one of coach's groups
    student_result = await db.execute(
        select(Student)
        .join(Group)
        .where(Student.id == student_id, Group.coach_id == user.id)
    )
    student = student_result.scalar_one_or_none()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student not found or not in your groups"
        )

    # Get attendance records for this student
    attendance_query = select(Attendance).where(Attendance.student_id == student_id)

    if from_date or to_date:
        attendance_query = attendance_query.join(Session)
        if from_date:
            attendance_query = attendance_query.where(Session.session_date >= from_date)
        if to_date:
            attendance_query = attendance_query.where(Session.session_date <= to_date)

    attendances_result = await db.execute(attendance_query)
    attendances = attendances_result.scalars().all()

    present = sum(1 for a in attendances if a.status == AttendanceStatus.PRESENT)
    absent = sum(1 for a in attendances if a.status == AttendanceStatus.ABSENT)
    late = sum(1 for a in attendances if a.status == AttendanceStatus.LATE)
    total = len(attendances)

    attendance_rate = (present / total * 100) if total > 0 else 0.0

    # Get total sessions count
    sessions_query = select(func.count(Session.id)).join(Group).where(
        Group.id == student.group_id
    )
    if from_date:
        sessions_query = sessions_query.where(Session.session_date >= from_date)
    if to_date:
        sessions_query = sessions_query.where(Session.session_date <= to_date)

    total_sessions_result = await db.execute(sessions_query)
    total_sessions = total_sessions_result.scalar() or 0

    return DataResponse(data=AttendanceStats(
        total_sessions=total_sessions,
        present_count=present,
        absent_count=absent,
        late_count=late,
        attendance_rate=round(attendance_rate, 2)
    ))


@router.get("/my-attendances", response_model=DataResponse[list[AttendanceRead]], dependencies=[Depends(require_permission(PERM_ATTENDANCE_COACH_MARK))])
async def get_coach_created_attendances(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    group_id: Optional[int] = None,
    student_id: Optional[int] = None,
):
    """
    Get all attendance records created by the coach (read-only).

    This endpoint allows coaches to view all attendances they have marked,
    including for all groups and students. Coaches cannot edit these records
    through this endpoint - it's read-only.

    Filters:
    - from_date: Filter by session date (start)
    - to_date: Filter by session date (end)
    - group_id: Filter by specific group
    - student_id: Filter by specific student
    """
    # Build query for attendances created by this coach
    attendance_query = select(Attendance).options(
        selectinload(Attendance.student),
        selectinload(Attendance.session).selectinload(Session.group),
        selectinload(Attendance.marked_by)
    ).where(Attendance.marked_by_user_id == user.id)

    # Apply date filters via session
    if from_date or to_date:
        attendance_query = attendance_query.join(Session)
        if from_date:
            attendance_query = attendance_query.where(Session.session_date >= from_date)
        if to_date:
            attendance_query = attendance_query.where(Session.session_date <= to_date)

    # Apply group filter via session
    if group_id:
        if not (from_date or to_date):  # Only join if not already joined
            attendance_query = attendance_query.join(Session)
        attendance_query = attendance_query.where(Session.group_id == group_id)

    # Apply student filter
    if student_id:
        attendance_query = attendance_query.where(Attendance.student_id == student_id)

    # Order by most recent first
    attendance_query = attendance_query.order_by(Attendance.created_at.desc())

    attendances_result = await db.execute(attendance_query)
    attendances = attendances_result.scalars().all()

    return DataResponse(data=[AttendanceRead.model_validate(a) for a in attendances])


@router.post("/sessions/{session_id}/upload-konspekt", response_model=DataResponse[SessionRead], dependencies=[Depends(require_permission(PERM_ATTENDANCE_COACH_MARK))])
async def upload_konspekt(
    session_id: int,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
):
    """
    Upload konspekt document to S3 and update session.
    Accepts: .pdf, .docx, .doc, images (.jpg, .jpeg, .png)

    Process:
    1. Coach marks attendance
    2. Coach uploads konspekt file with optional description (this endpoint)
    3. File is uploaded to S3 and session is updated with URL and description

    Form Data:
    - file: konspekt file (required)
    - description: optional description about the session
    """
    if not file_upload_service:
        raise HTTPException(
            status_code=500,
            detail="S3 service not configured. Please add AWS credentials to .env file: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME"
        )

    # Verify session exists and coach has access to it
    session_result = await db.execute(
        select(Session)
        .join(Group)
        .where(Session.id == session_id, Group.coach_id == user.id, Group.status != GroupStatus.DELETED)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or you do not have permission to upload konspekt"
        )

    # Validate file type
    allowed_extensions = ['.pdf', '.docx', '.doc', '.jpg', '.jpeg', '.png']
    file_ext = '.' + file.filename.split('.')[-1].lower() if '.' in file.filename else ''

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )

    try:
        # Upload to S3 in konspekts folder
        # Note: Bucket policy must allow public read for konspekts/*
        s3_url = await file_upload_service.upload_file(
            file=file,
            prefix="konspekts",
            make_public=True
        )

        # Update session with konspekt URL and description
        session.konspekt_url = s3_url
        if description is not None:
            session.description = description

        await db.commit()
        await db.refresh(session)

        return DataResponse(data=SessionRead.model_validate(session))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file: {str(e)}"
        )
