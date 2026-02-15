import base64
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_fernet() -> Fernet:
    secret_source = settings.token_encryption_key or settings.jwt_secret_key
    digest = hashlib.sha256(secret_source.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(user_id: UUID, company_id: UUID, expires_minutes: int, token_type: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(user_id),
        "company_id": str(company_id),
        "exp": expire,
        "type": token_type,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: UUID, company_id: UUID) -> str:
    return _create_token(user_id, company_id, settings.jwt_access_token_expire_minutes, "access")


def create_refresh_token(user_id: UUID, company_id: UUID) -> str:
    return _create_token(user_id, company_id, settings.jwt_refresh_token_expire_minutes, "refresh")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def encrypt_secret(secret: str) -> str:
    if not secret:
        return ""
    fernet = _get_fernet()
    return fernet.encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_secret: str) -> str:
    if not encrypted_secret:
        return ""
    fernet = _get_fernet()
    try:
        return fernet.decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted secret") from exc
