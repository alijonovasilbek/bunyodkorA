"""
Database backup service with Telegram integration.

This service automatically backs up the PostgreSQL database and sends it to a Telegram channel.
"""
import os
import gzip
import logging
from datetime import datetime
from pathlib import Path
import subprocess
from typing import Optional
from telegram import Bot
from telegram.error import TelegramError
from app.core.config import settings

logger = logging.getLogger(__name__)


class BackupService:
    """Service for creating and sending database backups to Telegram."""

    def __init__(self):
        self.bot: Optional[Bot] = None
        self.backup_dir = Path("backups")
        self.backup_dir.mkdir(exist_ok=True)

        # Initialize Telegram bot if configured
        if settings.TELEGRAM_BOT_TOKEN and settings.BACKUP_ENABLED:
            try:
                self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
                logger.info("Telegram bot initialized for backups")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram bot: {e}")
                self.bot = None

    async def create_database_backup(self) -> Optional[Path]:
        """
        Create a compressed PostgreSQL database backup.

        Returns:
            Path to the backup file, or None if backup failed
        """
        try:
            # Parse database URL
            db_url = settings.DATABASE_URL
            # Extract database connection details from URL
            # Format: postgresql+asyncpg://user:password@host:port/dbname
            if "://" in db_url:
                db_url = db_url.split("://")[1]
            if "@" in db_url:
                credentials, host_db = db_url.split("@")
                if ":" in credentials:
                    db_user, db_password = credentials.split(":")
                else:
                    db_user = credentials
                    db_password = ""
            else:
                logger.error("Invalid DATABASE_URL format")
                return None

            if "/" in host_db:
                host_port, db_name = host_db.split("/")
                if ":" in host_port:
                    db_host, db_port = host_port.split(":")
                else:
                    db_host = host_port
                    db_port = "5432"
            else:
                logger.error("Invalid DATABASE_URL format")
                return None

            # Generate backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"bunyodkor_backup_{timestamp}.sql"
            backup_path = self.backup_dir / backup_filename
            compressed_path = Path(f"{backup_path}.gz")

            # Set PGPASSWORD environment variable for pg_dump
            env = os.environ.copy()
            env["PGPASSWORD"] = db_password

            # Run pg_dump
            logger.info(f"Creating database backup: {backup_filename}")
            with open(backup_path, "w") as backup_file:
                result = subprocess.run(
                    [
                        "pg_dump",
                        "-h", db_host,
                        "-p", db_port,
                        "-U", db_user,
                        "-d", db_name,
                        "--no-owner",
                        "--no-acl",
                        "-F", "p",  # Plain text format
                    ],
                    env=env,
                    stdout=backup_file,
                    stderr=subprocess.PIPE,
                    text=True,
                )

            if result.returncode != 0:
                logger.error(f"pg_dump failed: {result.stderr}")
                if backup_path.exists():
                    backup_path.unlink()
                return None

            # Compress the backup
            logger.info(f"Compressing backup: {compressed_path}")
            with open(backup_path, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    f_out.writelines(f_in)

            # Remove uncompressed backup
            backup_path.unlink()

            # Get file size
            file_size_mb = compressed_path.stat().st_size / (1024 * 1024)
            logger.info(f"Backup created successfully: {compressed_path} ({file_size_mb:.2f} MB)")

            return compressed_path

        except Exception as e:
            logger.error(f"Failed to create database backup: {e}", exc_info=True)
            return None

    async def send_backup_to_telegram(self, backup_path: Path) -> bool:
        """
        Send backup file to Telegram channel.

        Args:
            backup_path: Path to the backup file

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.bot or not settings.TELEGRAM_CHAT_ID:
            logger.warning("Telegram bot not configured, skipping backup upload")
            return False

        try:
            file_size_mb = backup_path.stat().st_size / (1024 * 1024)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            caption = (
                f"🔄 Database Backup\n"
                f"📅 Date: {timestamp}\n"
                f"📦 Size: {file_size_mb:.2f} MB\n"
                f"🏢 Bunyodkor FastAPI System"
            )

            # Check file size (Telegram has a 50 MB limit for bots)
            if file_size_mb > 50:
                logger.warning(f"Backup file too large for Telegram ({file_size_mb:.2f} MB > 50 MB)")
                # Send notification instead
                await self.bot.send_message(
                    chat_id=settings.TELEGRAM_CHAT_ID,
                    text=f"⚠️ Backup created but too large to send via Telegram\n{caption}"
                )
                return False

            # Send the backup file
            logger.info(f"Sending backup to Telegram chat: {settings.TELEGRAM_CHAT_ID}")
            with open(backup_path, "rb") as backup_file:
                await self.bot.send_document(
                    chat_id=settings.TELEGRAM_CHAT_ID,
                    document=backup_file,
                    filename=backup_path.name,
                    caption=caption
                )

            logger.info("Backup sent to Telegram successfully")
            return True

        except TelegramError as e:
            logger.error(f"Failed to send backup to Telegram: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending backup to Telegram: {e}", exc_info=True)
            return False

    async def cleanup_old_backups(self, keep_last_n: int = 7):
        """
        Clean up old backup files, keeping only the most recent ones.

        Args:
            keep_last_n: Number of most recent backups to keep
        """
        try:
            # Get all backup files sorted by modification time (newest first)
            backup_files = sorted(
                self.backup_dir.glob("bunyodkor_backup_*.sql.gz"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

            # Remove old backups
            for backup_file in backup_files[keep_last_n:]:
                logger.info(f"Removing old backup: {backup_file.name}")
                backup_file.unlink()

        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}", exc_info=True)

    async def run_backup(self):
        """
        Main backup routine: create backup, send to Telegram, and cleanup old backups.
        """
        if not settings.BACKUP_ENABLED:
            logger.info("Backup is disabled in settings")
            return

        logger.info("Starting automated database backup...")

        try:
            # Create backup
            backup_path = await self.create_database_backup()
            if not backup_path:
                logger.error("Backup creation failed")
                # Send error notification to Telegram if bot is configured
                if self.bot and settings.TELEGRAM_CHAT_ID:
                    try:
                        await self.bot.send_message(
                            chat_id=settings.TELEGRAM_CHAT_ID,
                            text=f"❌ Database backup failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    except Exception:
                        pass
                return

            # Send to Telegram
            await self.send_backup_to_telegram(backup_path)

            # Cleanup old backups
            await self.cleanup_old_backups(keep_last_n=7)

            logger.info("Backup routine completed successfully")

        except Exception as e:
            logger.error(f"Backup routine failed: {e}", exc_info=True)


# Global backup service instance
backup_service = BackupService()
