import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException

from app.core.config import settings


PRIVATE_FILE_TTL_SECONDS = 180


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def generate_private_file_token(key: str, expires_in: int = PRIVATE_FILE_TTL_SECONDS) -> str:
    payload = {
        "key": key,
        "exp": int(time.time()) + expires_in,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    encoded_payload = _b64encode(payload_bytes)
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64encode(signature)}"


def verify_private_file_token(token: str) -> dict:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Invalid file token") from exc

    expected_signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    actual_signature = _b64decode(encoded_signature)

    if not hmac.compare_digest(expected_signature, actual_signature):
        raise HTTPException(status_code=404, detail="Invalid file token")

    payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=404, detail="File link expired")

    return payload
