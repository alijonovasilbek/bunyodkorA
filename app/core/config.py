from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    DATABASE_URL: str

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    # 🔹 Database URL (avtomatik yig‘iladi)
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120  # 2 hours
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 240  # 7 days

    PAYME_MERCHANT_ID: str = ""
    PAYME_KEY: str = ""
    PAYME_CALLBACK_URL: str = ""

    CLICK_MERCHANT_ID: str = ""
    CLICK_SERVICE_ID: str = ""
    CLICK_SECRET_KEY: str = ""
    CLICK_CALLBACK_URL: str = ""
    CLICK_AUTH_USERNAME: str = ""
    CLICK_AUTH_PASSWORD: str = ""

    SMS_PROVIDER_API_KEY: str = ""
    SMS_PROVIDER_URL: str = ""

    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_BUCKET_NAME: str = ""
    AWS_REGION: str = ""

    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_BACKUP_BOT_TOKEN: str = ""
    TELEGRAM_BACKUP_CHAT_ID: str = ""
    TELEGRAM_STUDENT_BOT_TOKEN: str = ""
    TELEGRAM_ERROR_ALERTS_ENABLED: bool = True
    TELEGRAM_ERROR_BOT_TOKEN: str = ""
    TELEGRAM_ERROR_CHAT_ID: str = ""
    BACKUP_ENABLED: bool = True
    BACKUP_HOUR: int = 3  # Hour of day to run backup (0-23, default 3 AM)

    TIMEZONE: str = "Asia/Tashkent"
    CURRENCY: str = "UZS"

    SWAGGER_USERNAME: str = ""
    SWAGGER_PASSWORD: str = ""

    @property
    def backup_telegram_bot_token(self) -> str:
        return (self.TELEGRAM_BACKUP_BOT_TOKEN or self.TELEGRAM_BOT_TOKEN or "").strip()

    @property
    def backup_telegram_chat_id(self) -> str:
        return (self.TELEGRAM_BACKUP_CHAT_ID or self.TELEGRAM_CHAT_ID or "").strip()

    @property
    def error_telegram_bot_token(self) -> str:
        return (self.TELEGRAM_ERROR_BOT_TOKEN or self.TELEGRAM_BOT_TOKEN or "").strip()

    @property
    def error_telegram_chat_id(self) -> str:
        return (self.TELEGRAM_ERROR_CHAT_ID or self.TELEGRAM_CHAT_ID or "").strip()

    class Config:
        env_file = ".env"


settings = Settings()
