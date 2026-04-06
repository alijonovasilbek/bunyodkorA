import json
import logging
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from app.core.config import settings


class TelegramErrorLogHandler(logging.Handler):
    _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tg-error-log")

    def __init__(self, bot_token: str, chat_id: str):
        super().__init__(level=logging.ERROR)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._hostname = socket.gethostname()

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return

        try:
            message = self._build_message(record)
            for chunk in self._split_message(message):
                self._executor.submit(self._send_message, chunk)
        except Exception:
            self.handleError(record)

    def _build_message(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        base_message = record.getMessage()

        lines = [
            "ERROR ALERT",
            f"time: {timestamp}",
            f"host: {self._hostname}",
            f"logger: {record.name}",
            f"level: {record.levelname}",
            f"message: {base_message}",
        ]

        if record.exc_info:
            exc_text = self.formatter.formatException(record.exc_info) if self.formatter else ""
            if exc_text:
                lines.append("traceback:")
                lines.append(exc_text)

        return "\n".join(lines)

    @staticmethod
    def _split_message(message: str, limit: int = 3900) -> list[str]:
        if len(message) <= limit:
            return [message]

        chunks: list[str] = []
        start = 0
        while start < len(message):
            end = min(start + limit, len(message))
            if end < len(message):
                split_at = message.rfind("\n", start, end)
                if split_at > start:
                    end = split_at
            chunks.append(message[start:end])
            start = end
            while start < len(message) and message[start] == "\n":
                start += 1
        return chunks

    def _send_message(self, text: str) -> None:
        payload = json.dumps(
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        request = Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=8):
            return


def setup_telegram_error_logging() -> bool:
    if not settings.TELEGRAM_ERROR_ALERTS_ENABLED:
        return False

    bot_token = settings.error_telegram_bot_token
    chat_id = settings.error_telegram_chat_id
    if not bot_token or not chat_id:
        return False

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, TelegramErrorLogHandler):
            return True

    handler = TelegramErrorLogHandler(bot_token=bot_token, chat_id=chat_id)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(handler)
    return True
