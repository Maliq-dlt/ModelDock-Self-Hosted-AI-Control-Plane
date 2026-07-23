import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.rate_limit import enforce_rate_limit
from app.models import APIKey, AdminUser


class CredentialConfigurationError(RuntimeError):
    pass


def hash_api_key(raw_key: str) -> str:
    secret = get_settings().api_key_hash_secret
    if not secret:
        raise CredentialConfigurationError("API_KEY_HASH_SECRET is required")
    return hmac.new(secret.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


def create_api_key(environment: str = "live") -> tuple[str, str, str]:
    raw_key = f"md_{environment}_{secrets.token_urlsafe(32)}"
    return raw_key, raw_key[:16], hash_api_key(raw_key)


def encrypt_credentials(credentials: dict) -> str:
    key = get_settings().credential_encryption_key
    if not key:
        raise CredentialConfigurationError("CREDENTIAL_ENCRYPTION_KEY is required to store provider credentials")
    return Fernet(key.encode()).encrypt(json.dumps(credentials).encode()).decode()


def decrypt_credentials(value: str | None) -> dict:
    if not value:
        return {}
    key = get_settings().credential_encryption_key
    if not key:
        raise CredentialConfigurationError("CREDENTIAL_ENCRYPTION_KEY is required to read provider credentials")
    try:
        return json.loads(Fernet(key.encode()).decrypt(value.encode()).decode())
    except (InvalidToken, ValueError, TypeError) as exc:
        raise CredentialConfigurationError("Provider credentials cannot be decrypted") from exc


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt_value, digest_value = encoded.split("$", 2)
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=_unb64(salt_value), n=2**14, r=8, p=1)
        return hmac.compare_digest(digest, _unb64(digest_value))
    except (ValueError, TypeError):
        return False


def create_admin_token(user: AdminUser) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": user.id, "role": user.role, "iat": now, "exp": now + 8 * 60 * 60}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}"
    secret = (get_settings().admin_session_secret or get_settings().admin_api_key).encode()
    signature = _b64(hmac.new(secret, signing_input.encode(), hashlib.sha256).digest())
    return f"md_admin_{signing_input}.{signature}"


def verify_admin_token(token: str) -> dict:
    if not token.startswith("md_admin_"):
        raise ValueError("invalid admin token")
    value = token.removeprefix("md_admin_")
    parts = value.split(".")
    if len(parts) != 3:
        raise ValueError("invalid admin token")
    signing_input = f"{parts[0]}.{parts[1]}"
    secret = (get_settings().admin_session_secret or get_settings().admin_api_key).encode()
    expected = _b64(hmac.new(secret, signing_input.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):
        raise ValueError("invalid admin token")
    payload = json.loads(_unb64(parts[1]))
    if int(payload.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("admin token expired")
    return payload


async def require_admin(
    x_modeldock_admin_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> AdminUser | None:
    expected = get_settings().admin_api_key
    if expected and x_modeldock_admin_key and hmac.compare_digest(x_modeldock_admin_key, expected):
        return None
    if authorization and authorization.startswith("Bearer md_admin_"):
        try:
            payload = verify_admin_token(authorization.removeprefix("Bearer ").strip())
            user = await session.get(AdminUser, payload["sub"])
            if user and user.active:
                return user
        except (ValueError, KeyError, TypeError):
            pass
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required")


def require_admin_role(*roles: str):
    async def dependency(user: AdminUser | None = Depends(require_admin)) -> AdminUser | None:
        if user is not None and user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient admin role")
        return user

    return dependency


async def require_api_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> APIKey:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer API key required")
    raw_key = authorization.removeprefix("Bearer ").strip()
    try:
        key_hash = hash_api_key(raw_key)
    except CredentialConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    api_key = await session.scalar(select(APIKey).where(APIKey.key_hash == key_hash))
    if not api_key or api_key.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    if api_key.expires_at and api_key.expires_at <= utc_now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")
    api_key.last_used_at = utc_now()
    await session.commit()
    client_ip = request.client.host if request.client else None
    if api_key.allowed_ips_json and client_ip not in api_key.allowed_ips_json:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client IP is not allowed")
    await enforce_rate_limit(api_key.id, api_key.rate_limit_rpm)
    request.state.api_key = api_key
    return api_key
