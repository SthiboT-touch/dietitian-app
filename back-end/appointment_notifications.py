"""Email notifications for appointment workflows."""

import config
import resend
from resend.exceptions import NoContentError, ResendError


class AppointmentNotificationError(Exception):
    """Raised when an appointment notification cannot be delivered."""


def send_appointment_created_email(
    *,
    recipient_email: str,
    dietitian_name: str,
    client_name: str,
    client_email: str,
    appointment: dict,
) -> None:
    if not config.RESEND_API_KEY or not config.RESEND_FROM_EMAIL:
        raise AppointmentNotificationError(
            "Appointment email delivery is not configured."
        )

    appointment_date = appointment["appointment_date"]
    appointment_details = (
        f"Appointment ID: {appointment['appointment_id']}\n"
        f"Date and time: {appointment_date}\n"
        f"Appointment type: {appointment['appointment_type']}\n"
        f"Consultation type: {appointment['consultation_type']}\n"
        f"Visit type: {appointment['visit_type']}\n"
        f"Duration: {appointment['duration']} minutes\n"
        f"Branch: {appointment.get('branch_id') or 'Not specified'}\n"
        f"Status: {appointment['status']}"
    )
    payload = {
        "from": config.RESEND_FROM_EMAIL,
        "to": [recipient_email],
        "subject": "New appointment request",
        "text": (
            f"Hello {dietitian_name},\n\n"
            "A client has requested an appointment with you.\n\n"
            f"Client: {client_name}\n"
            f"Client email: {client_email}\n\n"
            f"{appointment_details}\n\n"
            "Please sign in to NutriCare to review the request."
        ),
    }

    try:
        resend.api_key = config.RESEND_API_KEY
        resend.default_http_client = resend.RequestsClient(timeout=15)
        resend.Emails.send(payload)
    except ResendError as error:
        raise AppointmentNotificationError(
            f"Resend rejected the appointment notification (HTTP {error.code})."
        ) from error
    except NoContentError as error:
        raise AppointmentNotificationError(
            "Resend returned an empty response for the appointment notification."
        ) from error
    except (TimeoutError, OSError) as error:
        raise AppointmentNotificationError(
            "Appointment email delivery is temporarily unavailable."
        ) from error
