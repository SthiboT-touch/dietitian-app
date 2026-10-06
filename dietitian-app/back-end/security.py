"""Password hashing and bearer-session dependencies."""
import hashlib
import hmac
import ipaddress
import secrets
from fastapi import Header, HTTPException, Request as FastAPIRequest
from typing import Optional
from state import admin_sessions_db, dietitian_sessions_db


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, digest_hex = password_hash.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return hmac.compare_digest(actual_digest, expected_digest)


def public_user(user: dict) -> dict:
    return {key: value for key, value in user.items() if key != "password_hash"}


def request_is_loopback(request: FastAPIRequest) -> bool:
    if not request.client:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def require_admin(authorization: Optional[str] = Header(default=None)) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or token not in admin_sessions_db:
        raise HTTPException(status_code=401, detail="Admin sign-in required")
    return admin_sessions_db[token]


def require_dietitian(authorization: Optional[str] = Header(default=None)) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or token not in dietitian_sessions_db:
        raise HTTPException(status_code=401, detail="Dietitian sign-in required")
    return dietitian_sessions_db[token]
