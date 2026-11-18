"""Resend email delivery and server-side one-time-code verification."""

import hashlib
import hmac
import secrets
import time

import config
import resend
from resend.exceptions import NoContentError, ResendError


class EmailVerificationError(Exception):
    """A safe, user-facing error from email verification."""


_challenges: dict[str, dict] = {}
_last_sent: dict[str, float] = {}


def email_verification_enabled() -> bool:
    return bool(config.RESEND_API_KEY and config.RESEND_FROM_EMAIL)


def _code_digest(method_id: str, email: str, code: str, purpose: str) -> bytes:
    message = f"{purpose}:{method_id}:{email}:{code}".encode()
    return hmac.new(config.RESEND_API_KEY.encode(), message, hashlib.sha256).digest()


def _send_code(
    email: str, purpose: str, context: tuple[str, str] | None = None
) -> dict:
    if not email_verification_enabled():
        raise EmailVerificationError(
            "Email verification is not configured. Add RESEND_API_KEY and RESEND_FROM_EMAIL to the server environment."
        )

    now = time.time()
    normalized_email = email.strip().casefold()
    for method_id, challenge in list(_challenges.items()):
        if challenge["expires_at"] <= now or challenge["attempts"] >= 5:
            _challenges.pop(method_id, None)
    for sent_email, sent_at in list(_last_sent.items()):
        if now - sent_at > 3600:
            _last_sent.pop(sent_email, None)
    last_sent = _last_sent.get(normalized_email)
    if last_sent and now - last_sent < 60:
        raise EmailVerificationError("Please wait a minute before requesting another code.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    method_id = secrets.token_urlsafe(24)
    is_password_reset = purpose == "password_reset"
    code_instructions = (
        "Use this 6-digit code to reset your NutriCare password:\n\n"
        if is_password_reset
        else "Use this 6-digit code to verify your NutriCare email address:\n\n"
    )
    payload = {
        "from": config.RESEND_FROM_EMAIL,
        "to": [email],
        "subject": (
            "Reset your NutriCare password"
            if is_password_reset
            else "Verify your NutriCare account"
        ),
        "text": (
            "Hello,\n\n"
            + code_instructions
            + f"{code}\n\n"
            + "This code expires in 5 minutes. If you did not request it, you can ignore this email."
        ),
    }
    try:
        # Match the tutorial: load the key from the server environment, then send
        # through the official SDK. Keep the existing request timeout.
        resend.api_key = config.RESEND_API_KEY
        resend.default_http_client = resend.RequestsClient(timeout=15)
        result = resend.Emails.send(payload)
    except ResendError as error:
        status_code = str(error.code)
        provider_detail = f" Resend said: {error.message}" if error.message else ""
        if status_code == "401":
            message = (
                "Resend rejected the API key (HTTP 401). Check that RESEND_API_KEY is active and valid."
                f"{provider_detail}"
            )
        elif status_code == "403":
            message = (
                "Resend denied this sender (HTTP 403). Verify the sender's domain and "
                f"confirm this API key can send from that domain.{provider_detail}"
            )
        elif status_code == "422":
            message = (
                "Resend rejected the sender or email format (HTTP 422). Check RESEND_FROM_EMAIL "
                f"and verify the sender's domain.{provider_detail}"
            )
        elif status_code == "429":
            message = f"Resend rate limit reached. Wait a moment, then request a new code.{provider_detail}"
        else:
            message = f"Resend rejected the request (HTTP {status_code}): {error.message}"
        raise EmailVerificationError(message) from error
    except NoContentError as error:
        raise EmailVerificationError(
            "Resend returned an empty response. Please try again."
        ) from error
    except (TimeoutError, OSError) as error:
        raise EmailVerificationError(
            "Email verification is temporarily unavailable. Please try again."
        ) from error

    _challenges[method_id] = {
        "email": normalized_email,
        "digest": _code_digest(method_id, normalized_email, code, purpose),
        "purpose": purpose,
        "context": context,
        "expires_at": now + 300,
        "attempts": 0,
    }
    _last_sent[normalized_email] = now
    return {"enabled": True, "method_id": method_id, "request_id": result.get("id")}


def send_email_code(email: str) -> dict:
    return _send_code(email, "email_verification")


def send_password_reset_code(email: str, account: tuple[str, str]) -> dict:
    return _send_code(email, "password_reset", account)


def _verify_code(method_id: str, code: str, email: str, purpose: str) -> dict:
    if not email_verification_enabled():
        raise EmailVerificationError(
            "Email verification is not configured. Add RESEND_API_KEY and RESEND_FROM_EMAIL to the server environment."
        )

    normalized_email = email.strip().casefold()
    challenge = _challenges.get(method_id)
    if (
        not challenge
        or challenge.get("purpose") != purpose
        or challenge["email"] != normalized_email
    ):
        raise EmailVerificationError("That verification code is invalid or expired.")
    if challenge["expires_at"] <= time.time():
        _challenges.pop(method_id, None)
        raise EmailVerificationError("That verification code is invalid or expired.")

    supplied_digest = _code_digest(method_id, normalized_email, code, purpose)
    if not hmac.compare_digest(challenge["digest"], supplied_digest):
        challenge["attempts"] += 1
        if challenge["attempts"] >= 5:
            _challenges.pop(method_id, None)
        raise EmailVerificationError("That verification code is incorrect or expired.")

    context = challenge.get("context")
    _challenges.pop(method_id, None)
    return {
        "enabled": True,
        "verified": True,
        "user_id": None,
        "request_id": None,
        "context": context,
    }


def verify_email_code(method_id: str, code: str, email: str) -> dict:
    return _verify_code(method_id, code, email, "email_verification")


def verify_password_reset_code(method_id: str, code: str, email: str) -> dict:
    return _verify_code(method_id, code, email, "password_reset")
