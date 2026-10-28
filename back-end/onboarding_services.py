"""Small, privacy-conscious helpers for new patient onboarding (FR-1.4–1.9).

No outgoing messages or private files are processed unless explicitly provided by
registration. Secrets are never included in API responses or application logs.
"""
import base64
import binascii
import hashlib
import io
import re
import secrets
import smtplib
from email.message import EmailMessage
from os import environ
from fastapi import HTTPException

MAX_PHOTO_BYTES = 1024 * 1024
MAX_DOCUMENT_BYTES = 3 * 1024 * 1024
SAFE_NAME = re.compile(r"[^a-zA-Z0-9_. -]")


def validate_attachment(attachment, *, photo=False):
    """Decode bounded base64, inspect file signature and reject content mismatch."""
    if attachment is None:
        return None
    if attachment.filename != attachment.filename.rsplit('/', 1)[-1] or '\\' in attachment.filename:
        raise HTTPException(422, "Use a simple filename without a file path")
    filename = SAFE_NAME.sub('_', attachment.filename).strip('. ')
    if not filename or len(filename) > 120:
        raise HTTPException(422, "Invalid attachment filename")
    try:
        raw = base64.b64decode(attachment.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Invalid attachment encoding") from None
    limit = MAX_PHOTO_BYTES if photo else MAX_DOCUMENT_BYTES
    if not raw or len(raw) > limit:
        raise HTTPException(422, "Attachment exceeds the permitted size")
    mime = attachment.content_type
    if photo:
        if mime == "image/jpeg" and raw[:3] == b'\xff\xd8\xff':
            pass
        elif mime == "image/png" and raw[:8] == b'\x89PNG\r\n\x1a\n':
            pass
        else:
            raise HTTPException(422, "Profile photo must be a JPEG or PNG image")
        # Keep stored images inert; decoding also detects truncated/corrupt images.
        try:
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
        except Exception:
            raise HTTPException(422, "Profile photo could not be read as an image") from None
    elif mime == "application/pdf":
        if not raw.startswith(b'%PDF-'):
            raise HTTPException(422, "Document content does not match PDF type")
    elif mime == "image/jpeg" and raw[:3] == b'\xff\xd8\xff':
        pass
    elif mime == "image/png" and raw[:8] == b'\x89PNG\r\n\x1a\n':
        pass
    else:
        raise HTTPException(422, "Document must be PDF, JPEG or PNG")
    return {"filename": filename, "content_type": mime, "bytes": raw}


def new_checkin_credential():
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest()


def checkin_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def welcome_message(full_name):
    """No confidential health or ID information belongs in welcome email."""
    return (
        f"Hello {full_name},\n\n"
        "Welcome to NutriCare. Your patient account has been created. "
        "Sign in to review your profile, choose a dietitian and request an appointment.\n\n"
        "If you did not create this account, contact the practice through its official website.\n\n"
        "NutriCare Team"
    )


def smtp_is_configured():
    return all(environ.get(k) for k in ("WELCOME_SMTP_HOST", "WELCOME_FROM_EMAIL"))


def send_welcome_email(address, full_name):
    """Send over an explicitly configured SMTP connection; exceptions are retried by the worker."""
    if not smtp_is_configured():
        raise RuntimeError("SMTP delivery is not configured")
    message = EmailMessage()
    message["From"] = environ["WELCOME_FROM_EMAIL"]
    message["To"] = address
    message["Subject"] = "Welcome to NutriCare"
    message.set_content(welcome_message(full_name))
    host = environ["WELCOME_SMTP_HOST"]
    port = int(environ.get("WELCOME_SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        if environ.get("WELCOME_SMTP_USER"):
            smtp.login(environ["WELCOME_SMTP_USER"], environ.get("WELCOME_SMTP_PASSWORD", ""))
        smtp.send_message(message)


def qr_svg(value):
    """Generate an SVG QR code locally; never request an external QR service."""
    import qrcode
    from qrcode.image.svg import SvgPathImage
    code = qrcode.QRCode(border=3, box_size=5, error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(value)
    code.make(fit=True)
    buf = io.BytesIO()
    code.make_image(image_factory=SvgPathImage).save(buf)
    return buf.getvalue().decode('utf-8')
