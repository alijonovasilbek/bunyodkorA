from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.core.db import get_db
from app.core.permissions import PERM_CONTRACTS_EDIT, PERM_CONTRACTS_VIEW
from app.models.domain import WaitingList, Group
from app.schemas.waiting_list import WaitingListCreate, WaitingListUpdate, WaitingListRead
from app.schemas.common import DataResponse, PaginationMeta
from app.deps import require_permission
from app.models.auth import User

router = APIRouter(prefix="/waiting-list", tags=["Waiting List"])


@router.get("", response_model=DataResponse[list[WaitingListRead]], dependencies=[Depends(require_permission(PERM_CONTRACTS_VIEW))])
async def get_waiting_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    group_id: Optional[int] = None,
    birth_year: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    Get waiting list entries for prospective students.

    Filter by group_id to see all students waiting for a specific group.
    Filter by birth_year to see students of a specific birth year.

    Results are ordered by priority (high to low), then by created_at (oldest first).
    """
    query = select(WaitingList).order_by(WaitingList.priority.desc(), WaitingList.created_at)

    if group_id:
        query = query.where(WaitingList.group_id == group_id)
    if birth_year:
        query = query.where(WaitingList.birth_year == birth_year)

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    waiting_list = result.scalars().all()

    # Count total
    count_query = select(func.count(WaitingList.id))
    if group_id:
        count_query = count_query.where(WaitingList.group_id == group_id)
    if birth_year:
        count_query = count_query.where(WaitingList.birth_year == birth_year)

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return DataResponse(
        data=[WaitingListRead.model_validate(w) for w in waiting_list],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.post("", response_model=DataResponse[WaitingListRead])
async def add_to_waiting_list(
    data: WaitingListCreate,
    user: Annotated[User, Depends(require_permission(PERM_CONTRACTS_EDIT))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Add a prospective student to waiting list for a group.

    Used when a group is full and a new student (not yet registered) needs to wait for a slot.
    Stores all student and parent information directly - no need to create a student record first.
    """
    # Check if group exists
    group_result = await db.execute(select(Group).where(Group.id == data.group_id))
    group = group_result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail=f"Group with ID {data.group_id} not found")

    # Validate birth year matches group's birth year
    if group.birth_year != data.birth_year:
        raise HTTPException(
            status_code=400,
            detail=f"Student birth year ({data.birth_year}) does not match group's birth year ({group.birth_year})"
        )

    # Check for duplicate entry (same name, birth year, and group)
    existing = await db.execute(
        select(WaitingList).where(
            and_(
                WaitingList.student_first_name == data.student_first_name,
                WaitingList.student_last_name == data.student_last_name,
                WaitingList.birth_year == data.birth_year,
                WaitingList.group_id == data.group_id
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Student {data.student_first_name} {data.student_last_name} (born {data.birth_year}) "
                   f"is already in the waiting list for this group"
        )

    # Validate parent information - at least one parent contact is required
    if not data.father_phone and not data.mother_phone:
        raise HTTPException(
            status_code=400,
            detail="At least one parent phone number (father or mother) is required"
        )

    waiting_entry = WaitingList(
        student_first_name=data.student_first_name,
        student_last_name=data.student_last_name,
        birth_year=data.birth_year,
        father_name=data.father_name,
        father_phone=data.father_phone,
        mother_name=data.mother_name,
        mother_phone=data.mother_phone,
        group_id=data.group_id,
        priority=data.priority,
        notes=data.notes,
        added_by_user_id=user.id
    )

    db.add(waiting_entry)
    await db.commit()
    await db.refresh(waiting_entry)

    return DataResponse(data=WaitingListRead.model_validate(waiting_entry))


@router.get("/{waiting_id}", response_model=DataResponse[WaitingListRead], dependencies=[Depends(require_permission(PERM_CONTRACTS_VIEW))])
async def get_waiting_list_entry(
    waiting_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a specific waiting list entry by ID."""
    result = await db.execute(select(WaitingList).where(WaitingList.id == waiting_id))
    waiting_entry = result.scalar_one_or_none()

    if not waiting_entry:
        raise HTTPException(status_code=404, detail="Waiting list entry not found")

    return DataResponse(data=WaitingListRead.model_validate(waiting_entry))


@router.patch("/{waiting_id}", response_model=DataResponse[WaitingListRead], dependencies=[Depends(require_permission(PERM_CONTRACTS_EDIT))])
async def update_waiting_list_entry(
    waiting_id: int,
    data: WaitingListUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a waiting list entry.

    Can update student info, parent info, priority, or notes.
    """
    result = await db.execute(select(WaitingList).where(WaitingList.id == waiting_id))
    waiting_entry = result.scalar_one_or_none()

    if not waiting_entry:
        raise HTTPException(status_code=404, detail="Waiting list entry not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(waiting_entry, field, value)

    await db.commit()
    await db.refresh(waiting_entry)

    return DataResponse(data=WaitingListRead.model_validate(waiting_entry))


@router.delete("/{waiting_id}", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_CONTRACTS_EDIT))])
async def remove_from_waiting_list(
    waiting_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Remove a prospective student from waiting list.

    Use this when:
    - Student gets registered and receives a contract slot
    - Student no longer wants to join this group
    - Entry is no longer valid
    """
    result = await db.execute(select(WaitingList).where(WaitingList.id == waiting_id))
    waiting_entry = result.scalar_one_or_none()

    if not waiting_entry:
        raise HTTPException(status_code=404, detail="Waiting list entry not found")

    await db.delete(waiting_entry)
    await db.commit()

    return DataResponse(data={"message": "Student removed from waiting list successfully"})


@router.get("/group/{group_id}/next", response_model=DataResponse[WaitingListRead | None], dependencies=[Depends(require_permission(PERM_CONTRACTS_VIEW))])
async def get_next_in_queue(
    group_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get the next prospective student in queue for a group.

    Returns the waiting list entry with highest priority, or oldest if priorities are equal.
    Returns null if no one is waiting.

    Useful when a spot opens up (contract canceled or student leaves) and you want to know
    which prospective student should be contacted first.
    """
    result = await db.execute(
        select(WaitingList)
        .where(WaitingList.group_id == group_id)
        .order_by(WaitingList.priority.desc(), WaitingList.created_at)
        .limit(1)
    )
    next_entry = result.scalar_one_or_none()

    if not next_entry:
        return DataResponse(data=None)

    return DataResponse(data=WaitingListRead.model_validate(next_entry))
