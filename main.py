from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import pytz  # ✅ Qo'shildi
from app.routers import (
    auth,
    users,
    roles,
    students,
    groups,
    contracts,
    coach,
    head_coach,
    gate,
    reports,
    settings,
    import_router,
    backup,
    waiting_list,
    uploads,
    archive,
)
from app.services.backup import backup_service
from app.services.telegram_error_logging import setup_telegram_error_logging
from app.core.config import settings as app_settings

import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configure Telegram error alerts for ERROR/CRITICAL logs.
telegram_error_logging_enabled = setup_telegram_error_logging()
if telegram_error_logging_enabled:
    logger.info("Telegram error alerts enabled")
else:
    logger.info("Telegram error alerts disabled or not configured")

# ✅ Timezone configuration
timezone = pytz.timezone(app_settings.TIMEZONE)  # "Asia/Tashkent"

# Initialize scheduler with timezone
scheduler = AsyncIOScheduler(timezone=timezone)  # ✅ Timezone qo'shildi


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.
    """
    # Startup
    logger.info("Starting Bunyodkor CIMS API...")

    # Initialize backup scheduler if enabled
    if app_settings.BACKUP_ENABLED:
        logger.info(
            f"Backup enabled - scheduling daily backups at {app_settings.BACKUP_HOUR}:00 "
            f"({app_settings.TIMEZONE})"  # ✅ Timezone ko'rsatish
        )

        # Schedule backup to run daily at specified hour in Tashkent timezone
        scheduler.add_job(
            backup_service.run_backup,
            trigger=CronTrigger(
                hour=app_settings.BACKUP_HOUR,
                minute=0,
                timezone=timezone  # ✅ Timezone qo'shildi
            ),
            id="daily_backup",
            name="Daily Database Backup",
            replace_existing=True,
        )

        # Start the scheduler
        scheduler.start()
        logger.info(
            f"Backup scheduler started - next run at {app_settings.BACKUP_HOUR}:00 "
            f"{app_settings.TIMEZONE}"
        )

        # ✅ Keyingi backup vaqtini ko'rsatish
        next_run = scheduler.get_job("daily_backup").next_run_time
        logger.info(f"Next backup scheduled for: {next_run}")
    else:
        logger.info("Backup is disabled in configuration")

    yield

    # Shutdown
    logger.info("Shutting down Bunyodkor CIMS API...")
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Backup scheduler stopped")


app = FastAPI(
    title="BUNYODKOR CIMS API",
    description="Comprehensive management system for Bunyodkor Football Academy",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

security = HTTPBasic()

def swagger_auth(
    credentials: HTTPBasicCredentials = Depends(security),
):
    if not app_settings.SWAGGER_USERNAME or not app_settings.SWAGGER_PASSWORD:
        raise HTTPException(status_code=404)

    valid_user = secrets.compare_digest(
        credentials.username, app_settings.SWAGGER_USERNAME
    )
    valid_pass = secrets.compare_digest(
        credentials.password, app_settings.SWAGGER_PASSWORD
    )

    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bunyodkor-fa-cims-git-dev-mirzohiddev006s-projects.vercel.app",
        "https://bunyodkor-fa-cims.vercel.app",
        "https://bunyodkor.cognilabs.org",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/docs", include_in_schema=False)
def protected_docs(_: None = Depends(swagger_auth)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="BUNYODKOR CIMS API (Admin Swagger)",
    )


@app.get("/openapi.json", include_in_schema=False)
def protected_openapi(_: None = Depends(swagger_auth)):
    return app.openapi()



@app.get("/health")
async def health_check():
    """Health check endpoint with scheduler status"""
    scheduler_status = "running" if scheduler.running else "stopped"
    next_backup = None

    if scheduler.running and app_settings.BACKUP_ENABLED:
        job = scheduler.get_job("daily_backup")
        if job:
            next_backup = job.next_run_time.isoformat() if job.next_run_time else None

    return {
        "status": "ok",
        "service": "bunyodkor-cims",
        "scheduler": scheduler_status,
        "backup_enabled": app_settings.BACKUP_ENABLED,
        "next_backup": next_backup,
        "timezone": app_settings.TIMEZONE
    }




app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(students.router)
app.include_router(groups.router)
app.include_router(contracts.router)
app.include_router(coach.router)
app.include_router(head_coach.router)
app.include_router(gate.router)
app.include_router(reports.router)
app.include_router(settings.router)
app.include_router(import_router.router)
app.include_router(backup.router)
app.include_router(waiting_list.router)
app.include_router(uploads.router)
app.include_router(archive.router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8008, reload=True)
