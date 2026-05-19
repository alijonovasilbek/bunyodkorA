from typing import Annotated, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from app.core.db import get_db
from app.core.permissions import PERM_SESSIONS_CREATE, PERM_SESSIONS_MANAGE
from app.models.domain import Group, GroupStatus, GroupGame
from app.models.attendance import Session, Attendance
from app.schemas.group import GroupRead
from app.schemas.attendance import (
    SessionRead,
    SessionCreate,
    SessionWithAttendances,
    BulkSessionCreate,
)
from app.schemas.game import GameCreate, GameUpdate, GameRead
from app.schemas.common import DataResponse
from app.deps import require_permission, CurrentUser

router = APIRouter(prefix="/head-coach", tags=["Head Coach"])


@router.get("/groups", response_model=DataResponse[list[GroupRead]], dependencies=[Depends(require_permission(PERM_SESSIONS_CREATE))])
async def get_all_active_groups(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    birth_year: Optional[int] = Query(None),
):
    """Get all active groups (exclude deleted groups) for session creation"""
    query = select(Group).where(Group.status != GroupStatus.DELETED)

    if birth_year:
        query = query.where(Group.birth_year == birth_year)

    result = await db.execute(query.order_by(Group.name))
    groups = result.scalars().all()
    return DataResponse(data=[GroupRead.model_validate(g) for g in groups])


@router.post("/sessions", response_model=DataResponse[SessionRead], dependencies=[Depends(require_permission(PERM_SESSIONS_CREATE))])
async def create_training_session(
    data: SessionCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new training session for any group.
    Head Coach can create sessions for all active groups with basic info only.

    Fields:
    - group_id: The group for which the session is being created
    - session_date: Date of the training session
    - topic: Topic/theme of the session
    - start_time: Start time (e.g., "10:00")
    - end_time: End time (e.g., "12:00")
    - station: Training station/location

    Note: description can be provided by Head Coach, while konspekt is added later by Coach.
    """
    # Verify the group exists and is not deleted
    group_result = await db.execute(
        select(Group).where(Group.id == data.group_id, Group.status != GroupStatus.DELETED)
    )
    group = group_result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=404,
            detail="Group not found or has been deleted"
        )

    # Create session (konspekt is added later by Coach)
    session = Session(
        session_date=data.session_date,
        topic=data.topic,
        start_time=data.start_time,
        end_time=data.end_time,
        description=data.description,
        station=data.station,
        group_id=data.group_id,
        created_by_user_id=user.id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return DataResponse(data=SessionRead.model_validate(session))


@router.post("/sessions/bulk", response_model=DataResponse[list[SessionRead]], dependencies=[Depends(require_permission(PERM_SESSIONS_CREATE))])
async def create_training_sessions_bulk(
    data: BulkSessionCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create multiple training sessions in one request.
    """
    if not data.sessions:
        raise HTTPException(status_code=400, detail="No sessions provided")

    requested_group_ids = {item.group_id for item in data.sessions}
    groups_result = await db.execute(
        select(Group.id).where(
            Group.id.in_(requested_group_ids),
            Group.status != GroupStatus.DELETED
        )
    )
    existing_group_ids = set(groups_result.scalars().all())
    missing_group_ids = sorted(requested_group_ids - existing_group_ids)
    if missing_group_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Group(s) not found or deleted: {missing_group_ids}"
        )

    sessions_to_create = [
        Session(
            session_date=item.session_date,
            topic=item.topic,
            start_time=item.start_time,
            end_time=item.end_time,
            description=item.description,
            station=item.station,
            group_id=item.group_id,
            created_by_user_id=user.id,
        )
        for item in data.sessions
    ]

    db.add_all(sessions_to_create)
    await db.commit()
    for session in sessions_to_create:
        await db.refresh(session)

    return DataResponse(data=[SessionRead.model_validate(s) for s in sessions_to_create])


@router.get("/sessions", response_model=DataResponse[list[SessionRead]], dependencies=[Depends(require_permission(PERM_SESSIONS_MANAGE))])
async def get_all_sessions(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    date_filter: Optional[date] = Query(None, alias="date"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    group_id: Optional[int] = Query(None),
):
    """
    Get all training sessions with optional filters.
    Head Coach can view all sessions.
    """
    if date_filter is not None and (from_date is not None or to_date is not None):
        raise HTTPException(
            status_code=400,
            detail="Use either 'date' or 'from_date/to_date' filters, not both"
        )

    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be before or equal to to_date")

    query = select(Session).join(Group).where(Group.status != GroupStatus.DELETED)

    if date_filter:
        query = query.where(Session.session_date == date_filter)
    else:
        if from_date:
            query = query.where(Session.session_date >= from_date)
        if to_date:
            query = query.where(Session.session_date <= to_date)

    if group_id:
        query = query.where(Session.group_id == group_id)

    query = query.order_by(Session.session_date.desc())

    result = await db.execute(query)
    sessions = result.scalars().all()
    return DataResponse(data=[SessionRead.model_validate(s) for s in sessions])


@router.get("/sessions/{session_id}", response_model=DataResponse[SessionWithAttendances], dependencies=[Depends(require_permission(PERM_SESSIONS_MANAGE))])
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
        .where(Session.id == session_id, Group.status != GroupStatus.DELETED)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or group has been deleted"
        )

    return DataResponse(data=SessionWithAttendances.model_validate(session))


@router.put("/sessions/{session_id}", response_model=DataResponse[SessionRead], dependencies=[Depends(require_permission(PERM_SESSIONS_MANAGE))])
async def update_training_session(
    session_id: int,
    data: SessionCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update existing training session.
    Head Coach can update session basic info and description.
    """
    # Verify session exists
    session_result = await db.execute(
        select(Session)
        .join(Group)
        .where(Session.id == session_id, Group.status != GroupStatus.DELETED)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or group has been deleted"
        )

    # Verify new group exists if changing group
    if data.group_id != session.group_id:
        group_result = await db.execute(
            select(Group).where(Group.id == data.group_id, Group.status != GroupStatus.DELETED)
        )
        group = group_result.scalar_one_or_none()

        if not group:
            raise HTTPException(
                status_code=404,
                detail="New group not found or has been deleted"
            )

    # Update session fields
    session.session_date = data.session_date
    session.topic = data.topic
    session.start_time = data.start_time
    session.end_time = data.end_time
    session.description = data.description
    session.station = data.station
    session.group_id = data.group_id

    await db.commit()
    await db.refresh(session)

    return DataResponse(data=SessionRead.model_validate(session))


@router.delete("/sessions/{session_id}", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_SESSIONS_MANAGE))])
async def delete_training_session(
    session_id: int,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete training session.
    Head Coach can delete sessions that haven't been completed yet.

    Note: Sessions with attendance records will also be deleted (cascade).
    """
    # Verify session exists
    session_result = await db.execute(
        select(Session)
        .options(selectinload(Session.attendances))
        .join(Group)
        .where(Session.id == session_id, Group.status != GroupStatus.DELETED)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or group has been deleted"
        )

    # Delete session (attendance records will cascade delete)
    await db.delete(session)
    await db.commit()

    return DataResponse(data={
        "message": "Session deleted successfully",
        "session_id": session_id,
        "deleted_attendances": len(session.attendances)
    })


# ─── Group Games ──────────────────────────────────────────────────────────────

@router.post(
    "/games",
    response_model=DataResponse[GameRead],
    dependencies=[Depends(require_permission(PERM_SESSIONS_CREATE))],
)
async def create_game(
    data: GameCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    group_result = await db.execute(
        select(Group).where(Group.id == data.group_id, Group.status != GroupStatus.DELETED)
    )
    if not group_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Group not found or has been deleted")

    game = GroupGame(
        group_id=data.group_id,
        game_date=data.game_date,
        game_name=data.game_name,
        start_time=data.start_time,
        end_time=data.end_time,
        stadium=data.stadium,
        description=data.description,
        created_by_user_id=user.id,
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)
    return DataResponse(data=GameRead.model_validate(game))


@router.get(
    "/games",
    response_model=DataResponse[list[GameRead]],
    dependencies=[Depends(require_permission(PERM_SESSIONS_MANAGE))],
)
async def get_all_games(
    db: Annotated[AsyncSession, Depends(get_db)],
    group_id: Optional[int] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
):
    query = (
        select(GroupGame)
        .join(Group)
        .where(Group.status != GroupStatus.DELETED)
        .order_by(GroupGame.game_date.desc())
    )
    if group_id:
        query = query.where(GroupGame.group_id == group_id)
    if from_date:
        query = query.where(GroupGame.game_date >= from_date)
    if to_date:
        query = query.where(GroupGame.game_date <= to_date)

    games = (await db.execute(query)).scalars().all()
    return DataResponse(data=[GameRead.model_validate(g) for g in games])


@router.get(
    "/games/{game_id}",
    response_model=DataResponse[GameRead],
    dependencies=[Depends(require_permission(PERM_SESSIONS_MANAGE))],
)
async def get_game(
    game_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(GroupGame).join(Group).where(GroupGame.id == game_id, Group.status != GroupStatus.DELETED)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return DataResponse(data=GameRead.model_validate(game))


@router.put(
    "/games/{game_id}",
    response_model=DataResponse[GameRead],
    dependencies=[Depends(require_permission(PERM_SESSIONS_MANAGE))],
)
async def update_game(
    game_id: int,
    data: GameUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(GroupGame).join(Group).where(GroupGame.id == game_id, Group.status != GroupStatus.DELETED)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(game, field, value)

    await db.commit()
    await db.refresh(game)
    return DataResponse(data=GameRead.model_validate(game))


@router.delete(
    "/games/{game_id}",
    response_model=DataResponse[dict],
    dependencies=[Depends(require_permission(PERM_SESSIONS_MANAGE))],
)
async def delete_game(
    game_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(GroupGame).join(Group).where(GroupGame.id == game_id, Group.status != GroupStatus.DELETED)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    await db.delete(game)
    await db.commit()
    return DataResponse(data={"message": "Game deleted successfully", "game_id": game_id})
