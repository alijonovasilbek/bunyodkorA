"""
Archive management endpoints for yearly data archiving.
Only accessible by superusers.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from datetime import datetime

from app.core.db import get_db
from app.deps import CurrentUser, get_current_user
from app.models.domain import Group, Student
from app.models.auth import User
from app.models.enums import GroupStatus, StudentStatus
from app.schemas.common import DataResponse

router = APIRouter(prefix="/archive", tags=["Archive"])


@router.post("/year/{year}", response_model=DataResponse[dict])
async def archive_year_data(
    year: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Archive all data for a specific year (Groups, Students).

    **SUPERUSER ONLY**

    This endpoint:
    1. Sets all groups with archive_year={year} to status=ARCHIVED
    2. Sets all students with archive_year={year} to status=ARCHIVED
    Example: POST /archive/year/2025
    Result: All 2025 data becomes archived and hidden from default views

    **Important**: This action cannot be easily undone!
    """
    # Check if user is superuser
    if not user.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Only superusers can archive data"
        )

    # Validate year
    current_year = datetime.now().year
    if year > current_year:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot archive future year {year}"
        )

    if year < 2020:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid year {year}"
        )

    # Count items before archiving
    groups_count_result = await db.execute(
        select(func.count(Group.id)).where(
            Group.archive_year == year,
            Group.status != GroupStatus.ARCHIVED
        )
    )
    groups_count = groups_count_result.scalar() or 0

    students_count_result = await db.execute(
        select(func.count(Student.id)).where(
            Student.archive_year == year,
            Student.status != StudentStatus.ARCHIVED
        )
    )
    students_count = students_count_result.scalar() or 0

    # Archive groups
    await db.execute(
        update(Group)
        .where(
            Group.archive_year == year,
            Group.status != GroupStatus.ARCHIVED
        )
        .values(status=GroupStatus.ARCHIVED)
    )

    # Archive students
    await db.execute(
        update(Student)
        .where(
            Student.archive_year == year,
            Student.status != StudentStatus.ARCHIVED
        )
        .values(status=StudentStatus.ARCHIVED)
    )

    await db.commit()

    return DataResponse(data={
        "message": f"Successfully archived all data for year {year}",
        "year": year,
        "archived": {
            "groups": groups_count,
            "students": students_count,
        }
    })


@router.post("/unarchive/year/{year}", response_model=DataResponse[dict])
async def unarchive_year_data(
    year: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Unarchive all data for a specific year (UNDO archive operation).

    **SUPERUSER ONLY**

    This endpoint restores archived data back to ACTIVE status.
    Use with caution!
    """
    # Check if user is superuser
    if not user.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Only superusers can unarchive data"
        )

    # Count archived items
    groups_count_result = await db.execute(
        select(func.count(Group.id)).where(
            Group.archive_year == year,
            Group.status == GroupStatus.ARCHIVED
        )
    )
    groups_count = groups_count_result.scalar() or 0

    students_count_result = await db.execute(
        select(func.count(Student.id)).where(
            Student.archive_year == year,
            Student.status == StudentStatus.ARCHIVED
        )
    )
    students_count = students_count_result.scalar() or 0

    # Unarchive groups
    await db.execute(
        update(Group)
        .where(
            Group.archive_year == year,
            Group.status == GroupStatus.ARCHIVED
        )
        .values(status=GroupStatus.ACTIVE)
    )

    # Unarchive students
    await db.execute(
        update(Student)
        .where(
            Student.archive_year == year,
            Student.status == StudentStatus.ARCHIVED
        )
        .values(status=StudentStatus.ACTIVE)
    )

    await db.commit()

    return DataResponse(data={
        "message": f"Successfully unarchived all data for year {year}",
        "year": year,
        "unarchived": {
            "groups": groups_count,
            "students": students_count,
        }
    })


@router.get("/stats/{year}", response_model=DataResponse[dict])
async def get_archive_stats(
    year: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Get statistics about archivable/archived data for a year.

    Shows how many groups and students are:
    - Currently active (archivable)
    - Already archived
    """
    # Check if user is superuser
    if not user.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Only superusers can view archive stats"
        )

    # Active counts
    active_groups = await db.execute(
        select(func.count(Group.id)).where(
            Group.archive_year == year,
            Group.status == GroupStatus.ACTIVE
        )
    )
    active_groups_count = active_groups.scalar() or 0

    active_students = await db.execute(
        select(func.count(Student.id)).where(
            Student.archive_year == year,
            Student.status == StudentStatus.ACTIVE
        )
    )
    active_students_count = active_students.scalar() or 0

    # Archived counts
    archived_groups = await db.execute(
        select(func.count(Group.id)).where(
            Group.archive_year == year,
            Group.status == GroupStatus.ARCHIVED
        )
    )
    archived_groups_count = archived_groups.scalar() or 0

    archived_students = await db.execute(
        select(func.count(Student.id)).where(
            Student.archive_year == year,
            Student.status == StudentStatus.ARCHIVED
        )
    )
    archived_students_count = archived_students.scalar() or 0

    return DataResponse(data={
        "year": year,
        "active": {
            "groups": active_groups_count,
            "students": active_students_count,
        },
        "archived": {
            "groups": archived_groups_count,
            "students": archived_students_count,
        }
    })
