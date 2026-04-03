from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.models.enums import UserStatus


class LoginRequest(BaseModel):
    phone_or_email: str
    password: str


class RegisterRequest(BaseModel):
    phone: str
    email: Optional[EmailStr] = None
    full_name: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PermissionRead(BaseModel):
    id: int
    code: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RoleRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RoleWithPermissions(RoleRead):
    permissions: list[PermissionRead] = []


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permission_ids: list[int] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[list[int]] = None


class UserRead(BaseModel):
    id: int
    phone: str
    email: Optional[str] = None
    full_name: str
    is_super_admin: bool
    status: UserStatus
    created_at: datetime

    class Config:
        from_attributes = True


class UserWithRoles(UserRead):
    roles: list[RoleRead] = []


class UserCreate(BaseModel):
    phone: str
    email: Optional[EmailStr] = None
    full_name: str
    password: str
    is_super_admin: bool = False
    status: UserStatus = UserStatus.ACTIVE


class UserUpdate(BaseModel):
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    status: Optional[UserStatus] = None


class UserRolesUpdate(BaseModel):
    role_ids: list[int]


class CurrentUserResponse(BaseModel):
    user: UserWithRoles
    permissions: list[str]


# Import GroupRead at the end to avoid circular imports
from app.schemas.group import GroupRead


class CoachWithGroups(UserRead):
    """Coach user with their assigned groups"""
    groups: list[GroupRead] = []

    class Config:
        from_attributes = True
