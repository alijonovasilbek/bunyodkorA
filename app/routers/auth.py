from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.db import get_db
from app.core.security import verify_password, create_access_token, hash_password, create_refresh_token, decode_refresh_token
from app.models.auth import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, CurrentUserResponse, UserWithRoles, PermissionRead, UserRead, RefreshTokenRequest
from app.deps import CurrentUser
from app.models.enums import UserStatus

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(User).where(
            (User.phone == credentials.phone_or_email) | (User.email == credentials.phone_or_email)
        )
    )
    user = result.scalars().first()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone/email or password",
        )

    # Check if user is deleted or inactive
    if user.status in [UserStatus.DELETED, UserStatus.INACTIVE]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active. Please contact administrator.",
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# @router.post("/register", response_model=UserRead)
# async def register(
#     data: RegisterRequest,
#     db: Annotated[AsyncSession, Depends(get_db)],
# ):
#     existing_phone = await db.execute(select(User).where(User.phone == data.phone))
#     if existing_phone.scalars().first():
#         raise HTTPException(status_code=400, detail="Phone number already registered")
#
#     if data.email:
#         existing_email = await db.execute(select(User).where(User.email == data.email))
#         if existing_email.scalars().first():
#             raise HTTPException(status_code=400, detail="Email already registered")
#
#     user = User(
#         phone=data.phone,
#         email=data.email,
#         full_name=data.full_name,
#         hashed_password=hash_password(data.password),
#         is_super_admin=False,
#         status=UserStatus.ACTIVE,
#     )
#     db.add(user)
#     await db.commit()
#     await db.refresh(user)
#
#     return UserRead.model_validate(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    request: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Refresh access token using a valid refresh token.

    Returns:
        New access token and refresh token
    """
    # Decode and validate refresh token
    payload = decode_refresh_token(request.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Get user ID from token
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Check if user is deleted or inactive
    if user.status in [UserStatus.DELETED, UserStatus.INACTIVE]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active. Please contact administrator.",
        )

    # Generate new tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=CurrentUserResponse)
async def get_current_user_info(user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.roles).selectinload(User.roles.property.mapper.class_.permissions)
        )
        .where(User.id == user.id)
    )
    user_with_relations = result.scalar_one()

    permissions = []
    if user.is_super_admin:
        from app.core.permissions import ALL_PERMISSIONS
        permissions = [p["code"] for p in ALL_PERMISSIONS]
    else:
        permission_set = set()
        for role in user_with_relations.roles:
            for perm in role.permissions:
                permission_set.add(perm.code)
        permissions = list(permission_set)

    return CurrentUserResponse(
        user=UserWithRoles.model_validate(user_with_relations),
        permissions=permissions,
    )
