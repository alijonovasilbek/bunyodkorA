from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.permissions import PERM_SETTINGS_SYSTEM_VIEW, PERM_SETTINGS_SYSTEM_EDIT
from app.models.settings import SystemSettings
from app.schemas.settings import SystemSettingsRead
from app.schemas.common import DataResponse
from app.deps import require_permission

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/system", response_model=DataResponse[list[SystemSettingsRead]], dependencies=[Depends(require_permission(PERM_SETTINGS_SYSTEM_VIEW))])
async def get_system_settings(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(SystemSettings))
    settings = result.scalars().all()
    return DataResponse(data=[SystemSettingsRead.model_validate(s) for s in settings])


@router.patch("/system", response_model=DataResponse[dict], dependencies=[Depends(require_permission(PERM_SETTINGS_SYSTEM_EDIT))])
async def update_system_settings(
    updates: dict[str, str],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    for key, value in updates.items():
        result = await db.execute(select(SystemSettings).where(SystemSettings.key == key))
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = value
        else:
            setting = SystemSettings(key=key, value=value)
            db.add(setting)

    await db.commit()
    return DataResponse(data={"message": "Settings updated successfully"})
