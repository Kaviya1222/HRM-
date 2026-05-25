from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.constants import ACCESS_TOKEN_TYPE, REFRESH_TOKEN_TYPE

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


class TokenPayload(BaseModel):
    sub: str
    sid: str
    jti: str
    typ: str
    role: str
    exp: int
    iat: int


def _pre_hash(password: str) -> str:
    """SHA-256 pre-hash to keep bcrypt input safely under its 72-byte limit."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(_pre_hash(plain_password), hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(_pre_hash(password))


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _create_token(*, subject: str, session_id: str, role_code: str, expires_delta: timedelta, token_type: str) -> tuple[str, str]:
    now = datetime.now(UTC)
    jti = str(uuid4())
    payload = {
        "sub": subject,
        "sid": session_id,
        "jti": jti,
        "typ": token_type,
        "role": role_code,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    return token, jti


def create_access_token(*, subject: str, session_id: str, role_code: str) -> tuple[str, str]:
    return _create_token(
        subject=subject,
        session_id=session_id,
        role_code=role_code,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        token_type=ACCESS_TOKEN_TYPE,
    )


def create_refresh_token(*, subject: str, session_id: str, role_code: str) -> tuple[str, str]:
    return _create_token(
        subject=subject,
        session_id=session_id,
        role_code=role_code,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        token_type=REFRESH_TOKEN_TYPE,
    )


def decode_token(token: str, expected_type: str | None = None) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        token_data = TokenPayload.model_validate(payload)
    except (JWTError, ValidationError) as exc:
        raise ValueError("Invalid token") from exc

    if expected_type and token_data.typ != expected_type:
        raise ValueError("Unexpected token type")

    return token_data
