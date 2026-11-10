"""Resend email delivery and server-side one-time-code verification."""

import hashlib
import hmac
import json
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config


class EmailVerificationError(Exception):
    """A safe, user-facing error from email verification."""


_challenges: dict[str, dict] = {}
_last_sent: dict[str, float] = {}


def email_verification_enabled() -> bool:
    return bool(config.RESEND_API_KEY and config.RESEND_FROM_EMAIL)


def _code_digest(method_id: str, email: str, code: str) -> bytes:
    message = f"{method_id}:{email}:{code}".encode()
    return hmac.new(config.RESEND_API_KEY.encode(), message, hashlib.sha256).digest()


def send_email_code(email: str) -> dict:
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
    payload = {
        "from": config.RESEND_FROM_EMAIL or env.get("RESEND_FROM_EMAIL", "onboarding@resend.dev"),
        "to": [email],
        "subject": "Verify your NutriCare account",
        "text": (
            "Hello,\n\n"
            "Use this 6-digit code to verify your NutriCare email address:\n\n"
            f"{code}\n\n"
            "This code expires in 5 minutes. If you did not request it, you can ignore this email."
        ),
    }
    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            body = {}
        message = body.get("message") if isinstance(body, dict) else None
        if not message and isinstance(body, dict):
            provider_error = body.get("error")
            message = (
                provider_error.get("message") or provider_error.get("name")
                if isinstance(provider_error, dict)
                else provider_error
            )
        if not message and error.code == 401:
            message = "Resend rejected the API key (HTTP 401). Check that RESEND_API_KEY is active and valid."
        elif not message and error.code == 403:
            message = (
                "Resend denied this sender (HTTP 403). Verify the sender's domain in Resend "
                "and confirm the API key has permission for that domain."
            )
        elif not message and error.code == 422:
            message = (
                "Resend rejected the sender or email format (HTTP 422). Check RESEND_FROM_EMAIL "
                "and verify the sender's domain."
            )
        elif not message and error.code == 429:
            message = "Resend rate limit reached. Wait a moment, then request a new code."
        elif not message:
            message = f"Resend rejected the request (HTTP {error.code}). Check the sender and API key settings."
        raise EmailVerificationError(
            str(message)
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise EmailVerificationError(
            "Email verification is temporarily unavailable. Please try again."
        ) from error
    except (ValueError, UnicodeDecodeError) as error:
        raise EmailVerificationError(
            "Resend returned an invalid response. Please try again."
        ) from error

    _challenges[method_id] = {
        "email": normalized_email,
        "digest": _code_digest(method_id, normalized_email, code),
        "expires_at": now + 300,
        "attempts": 0,
    }
    _last_sent[normalized_email] = now
    return {"enabled": True, "method_id": method_id, "request_id": result.get("id")}


def verify_email_code(method_id: str, code: str, email: str) -> dict:
    if not email_verification_enabled():
        raise EmailVerificationError(
            "Email verification is not configured. Add RESEND_API_KEY and RESEND_FROM_EMAIL to the server environment."
        )

    normalized_email = email.strip().casefold()
    challenge = _challenges.get(method_id)
    if (
        not challenge
        or challenge["email"] != normalized_email
        or challenge["expires_at"] <= time.time()
    ):
        _challenges.pop(method_id, None)
        raise EmailVerificationError("That verification code is invalid or expired.")

    supplied_digest = _code_digest(method_id, normalized_email, code)
    if not hmac.compare_digest(challenge["digest"], supplied_digest):
        challenge["attempts"] += 1
        if challenge["attempts"] >= 5:
            _challenges.pop(method_id, None)
        raise EmailVerificationError("That verification code is incorrect or expired.")

    _challenges.pop(method_id, None)
    return {"enabled": True, "verified": True, "user_id": None, "request_id": None}
