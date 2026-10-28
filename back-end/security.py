"""Password hashing and bearer-session dependencies."""
import hashlib
import hmac
import ipaddress
import secrets
from fastapi import Header, HTTPException, Request as FastAPIRequest
from typing import Optional
from state import admin_sessions_db, dietitian_sessions_db, client_sessions_db, staff_sessions_db, staff_accounts_db


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


def require_client(authorization: Optional[str] = Header(default=None)) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or token not in client_sessions_db:
        raise HTTPException(status_code=401, detail="Client sign-in required")
    return client_sessions_db[token]


# The existing login endpoints issue opaque bearer tokens into separate role stores.
# Keep that contract until a later, dedicated session-persistence migration.
def current_identity(authorization: Optional[str] = None) -> tuple[str, str]:
    """Return (role, account_id) for a valid existing bearer session."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Sign-in required")
    for role, sessions in (
        ("admin", admin_sessions_db),
        ("dietitian", dietitian_sessions_db),
        ("client", client_sessions_db),
    ):
        account_id = sessions.get(token)
        if account_id:
            return role, str(account_id)
    # Added BRS staff accounts do not inherit admin/clinical privileges.
    staff_id = staff_sessions_db.get(token)
    if staff_id:
        import config
        import database
        if config.DATABASE_ENABLED:
            with database.cursor() as cursor:
                cursor.execute(
                    "SELECT role, is_active FROM staff_account WHERE staff_id = %s",
                    (staff_id,),
                )
                staff = cursor.fetchone()
        else:
            staff = staff_accounts_db.get(staff_id)
        if staff and staff.get("is_active"):
            return (staff["role"], str(staff_id))
    raise HTTPException(status_code=401, detail="Sign-in required")


def client_is_assigned_to_dietitian(client_id: str, dietitian_id: str) -> bool:
    """Check assignment in the authoritative store (PostgreSQL or test store)."""
    import config
    import database
    from state import users_db

    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT dietitian_id FROM client WHERE client_id = %s", (client_id,))
            record = cursor.fetchone()
        return bool(record and str(record["dietitian_id"]) == str(dietitian_id))

    record = users_db.get(client_id)
    if not record or record.get("type") != "client":
        return False
    return str(record.get("dietitian_id")) == str(dietitian_id)


def authorize_client_access(client_id: str, identity: tuple[str, str]) -> None:
    """Enforce ownership/assignment before any clinical record is read or changed."""
    role, account_id = identity
    if role == "admin":
        return  # Existing system administrators have broad access; audit in later phase.
    if role == "client" and account_id == str(client_id):
        return
    if role == "dietitian" and client_is_assigned_to_dietitian(client_id, account_id):
        return
    raise HTTPException(status_code=403, detail="Not authorized for this client")


def require_client_record_access(
    request: FastAPIRequest, authorization: Optional[str] = Header(default=None)
) -> None:
    """Reusable route dependency for /clients/{client_id}/... endpoints."""
    identity = current_identity(authorization)
    authorize_client_access(request.path_params["client_id"], identity)
