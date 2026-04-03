from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from app.schemas.common import DataResponse
from app.deps import CurrentUser
from app.services.backup import backup_service
from app.core.config import settings

router = APIRouter(prefix="/backup", tags=["Backup"])


def require_super_admin(user: CurrentUser) -> CurrentUser:
    """Dependency to require super admin access."""
    if not user.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="This operation requires super admin privileges"
        )
    return user


@router.post("/manual", response_model=DataResponse[dict])
async def trigger_manual_backup(user: Annotated[CurrentUser, Depends(require_super_admin)]):
    """
    Manually trigger a database backup.

    This endpoint creates a database backup and sends it to the configured Telegram channel.
    Only available to super admin users.

    Returns:
        Success message with backup details
    """
    if not settings.BACKUP_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="Backup is disabled. Please enable BACKUP_ENABLED in configuration."
        )

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        raise HTTPException(
            status_code=400,
            detail="Telegram bot not configured. Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )

    try:
        # Run backup
        await backup_service.run_backup()

        return DataResponse(
            data={
                "message": "Manual backup completed successfully",
                "telegram_configured": bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@router.get("/status", response_model=DataResponse[dict])
async def get_backup_status(user: Annotated[CurrentUser, Depends(require_super_admin)]):
    """
    Get backup configuration status.

    Returns:
        Current backup configuration and status
    """
    return DataResponse(
        data={
            "backup_enabled": settings.BACKUP_ENABLED,
            "backup_hour": settings.BACKUP_HOUR,
            "telegram_configured": bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID),
            "telegram_chat_id": settings.TELEGRAM_CHAT_ID if settings.TELEGRAM_CHAT_ID else None,
        }
    )
