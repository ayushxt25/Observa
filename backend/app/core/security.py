from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import re

import jwt
from passlib.context import CryptContext

from app.core.config import Settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def create_access_token(settings: Settings, user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "typ": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"], audience=settings.jwt_audience, issuer=settings.jwt_issuer)
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise jwt.InvalidTokenError("Missing subject")
    return subject


def slugify(value: str, fallback: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or fallback
