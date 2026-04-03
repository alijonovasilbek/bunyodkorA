from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.core.db import get_db
from app.core.security import hash_password
from app.core.permissions import PERM_USERS_MANAGE
from app.models.auth import User, Role
from app.schemas.auth import UserRead, UserCreate, UserUpdate, UserRolesUpdate, UserWithRoles, CoachWithGroups
from app.schemas.common import DataResponse, PaginationMeta
from app.deps import require_permission, CurrentUser

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=DataResponse[list[UserWithRoles]], dependencies=[Depends(require_permission(PERM_USERS_MANAGE))])
async def get_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * page_size
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .order_by(User.created_at.desc())  # Order by most recent first
        .offset(offset)
        .limit(page_size)
    )
    users = result.scalars().all()

    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar()

    return DataResponse(
        data=[UserWithRoles.model_validate(u) for u in users],
        meta=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/coaches", response_model=DataResponse[list[CoachWithGroups]])
async def get_coaches(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get all users with 'Coach' role and their assigned groups (requires authentication)"""
    from app.models.enums import UserStatus
    from app.models.domain import Group
    from app.schemas.group import GroupRead

    # Find users who have the "Coach" role
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.status == UserStatus.ACTIVE)
    )
    all_users = result.scalars().all()

    coaches_with_groups = []
    for user_obj in all_users:
        # Check if user has "Coach" role (case-insensitive)
        has_coach_role = any(
            role.name.lower() == "coach" for role in user_obj.roles
        )

        if not has_coach_role:
            continue

        # Get groups assigned to this coach
        groups_result = await db.execute(
            select(Group).where(Group.coach_id == user_obj.id)
        )
        groups = groups_result.scalars().all()

        coach_data = CoachWithGroups(
            id=user_obj.id,
            phone=user_obj.phone,
            email=user_obj.email,
            full_name=user_obj.full_name,
            is_super_admin=user_obj.is_super_admin,
            status=user_obj.status,
            created_at=user_obj.created_at,
            groups=[GroupRead.model_validate(g) for g in groups]
        )
        coaches_with_groups.append(coach_data)

    return DataResponse(data=coaches_with_groups)


@router.post("", response_model=DataResponse[UserRead], dependencies=[Depends(require_permission(PERM_USERS_MANAGE))])
async def create_user(
    data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    existing_phone = await db.execute(select(User).where(User.phone == data.phone))
    if existing_phone.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Phone already registered")

    if data.email:
        existing_email = await db.execute(select(User).where(User.email == data.email))
        if existing_email.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="This email is already registered")

    user = User(
        phone=data.phone,
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        is_super_admin=data.is_super_admin,
        status=data.status,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return DataResponse(data=UserRead.model_validate(user))


@router.patch("/{user_id}", response_model=DataResponse[UserRead], dependencies=[Depends(require_permission(PERM_USERS_MANAGE))])
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.phone:
        existing_phone = await db.execute(select(User).where(User.phone == data.phone, User.id != user_id))
        if existing_phone.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Phone already registered")
        user.phone = data.phone

    if data.email:
        existing_email = await db.execute(select(User).where(User.email == data.email, User.id != user_id))
        if existing_email.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="This email is already registered")
        user.email = data.email

    if data.full_name:
        user.full_name = data.full_name
    if data.password:
        user.hashed_password = hash_password(data.password)
    if data.status:
        user.status = data.status

    await db.commit()
    await db.refresh(user)

    return DataResponse(data=UserRead.model_validate(user))


@router.get("/{user_id}", response_model=DataResponse[UserWithRoles], dependencies=[Depends(require_permission(PERM_USERS_MANAGE))])
async def get_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return DataResponse(data=UserWithRoles.model_validate(user))


@router.patch("/{user_id}/roles", response_model=DataResponse[UserWithRoles], dependencies=[Depends(require_permission(PERM_USERS_MANAGE))])
async def update_user_roles(
    user_id: int,
    data: UserRolesUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    roles_result = await db.execute(select(Role).where(Role.id.in_(data.role_ids)))
    roles = roles_result.scalars().all()

    if len(roles) != len(data.role_ids):
        raise HTTPException(status_code=400, detail="One or more role IDs are invalid")

    user.roles = roles
    await db.commit()
    await db.refresh(user, ["roles"])

    return DataResponse(data=UserWithRoles.model_validate(user))


@router.delete("/{user_id}", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_USERS_MANAGE))])
async def delete_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Permanently delete a user from the database.
    Super admin users cannot be deleted.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_super_admin:
        raise HTTPException(status_code=400, detail="Cannot delete super admin user")

    await db.delete(user)
    await db.commit()

    return DataResponse(data={"message": "User deleted successfully"})


@router.post("/bulk-delete", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_USERS_MANAGE))])
async def bulk_delete_users(
    user_ids: list[int],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Permanently delete multiple users from the database.
    Super admin users cannot be deleted.
    """
    if not user_ids:
        raise HTTPException(status_code=400, detail="No user IDs provided")

    deleted_count = 0
    errors = []

    for user_id in user_ids:
        try:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                errors.append({"user_id": user_id, "error": "User not found"})
                continue

            if user.is_super_admin:
                errors.append({"user_id": user_id, "error": "Cannot delete super admin user"})
                continue

            await db.delete(user)
            deleted_count += 1
        except Exception as e:
            errors.append({"user_id": user_id, "error": str(e)})

    await db.commit()

    return DataResponse(data={
        "message": f"Deleted {deleted_count} user(s)",
        "deleted_count": deleted_count,
        "total_requested": len(user_ids),
        "errors": errors if errors else None
    })
