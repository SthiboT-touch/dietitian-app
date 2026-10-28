"""Server-side Stytch Email OTP adapter."""

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config


class StytchEmailError(Exception):
    """A safe, user-facing error from Stytch."""


def _call(path: str, payload: dict) -> dict:
    credentials = f"{config.STYTCH_PROJECT_ID}:{config.STYTCH_SECRET}".encode("utf-8")
    headers = {
        "Authorization": "Basic " + base64.b64encode(credentials).decode("ascii"),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    request = Request(
        f"{config.STYTCH_API_BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            body = {}
        message = (
            body.get("error_message") or "Stytch could not process the email verification request."
        )
        raise StytchEmailError(message) from error
    except (URLError, TimeoutError) as error:
        raise StytchEmailError(
            "Email verification is temporarily unavailable. Please try again."
        ) from error


def send_email_code(email: str) -> dict:
    if not config.STYTCH_ENABLED:
        return {"enabled": False, "method_id": None}
    response = _call("/otps/email/send", {"email": email})
    return {
        "enabled": True,
        "method_id": response.get("email_id") or response.get("method_id"),
        "request_id": response.get("request_id"),
    }


def verify_email_code(method_id: str, code: str) -> dict:
    if not config.STYTCH_ENABLED:
        return {"enabled": False, "verified": False, "user_id": None}
    response = _call("/otps/authenticate", {"method_id": method_id, "code": code})
    return {
        "enabled": True,
        "verified": True,
        "user_id": (response.get("user") or {}).get("user_id") or response.get("user_id"),
        "request_id": response.get("request_id"),
    }
