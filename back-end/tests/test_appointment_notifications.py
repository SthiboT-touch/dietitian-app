import config
import pytest
import resend

from appointment_notifications import (
    AppointmentNotificationError,
    send_appointment_created_email,
)


def test_appointment_email_includes_client_and_appointment_details(monkeypatch):
    sent = {}
    monkeypatch.setattr(config, "RESEND_API_KEY", "test-api-key")
    monkeypatch.setattr(config, "RESEND_FROM_EMAIL", "care@example.com")
    monkeypatch.setattr(
        resend.Emails,
        "send",
        lambda payload: sent.update(payload) or {"id": "email-1"},
    )

    send_appointment_created_email(
        recipient_email="dietitian@example.com",
        dietitian_name="Avery Chen",
        client_name="Jordan Lee",
        client_email="jordan@example.com",
        appointment={
            "appointment_id": "appointment-1",
            "appointment_date": "2026-03-20T08:00:00+02:00",
            "appointment_type": "IN_PERSON",
            "consultation_type": "FOLLOW_UP",
            "visit_type": "follow_up",
            "duration": 50,
            "branch_id": "branch-1",
            "status": "PENDING",
        },
    )

    assert sent["to"] == ["dietitian@example.com"]
    assert sent["from"] == "care@example.com"
    assert "Jordan Lee" in sent["text"]
    assert "jordan@example.com" in sent["text"]
    assert "Appointment ID: appointment-1" in sent["text"]
    assert "Date and time: 2026-03-20T08:00:00+02:00" in sent["text"]
    assert "Consultation type: FOLLOW_UP" in sent["text"]


def test_appointment_email_requires_resend_configuration(monkeypatch):
    monkeypatch.setattr(config, "RESEND_API_KEY", "")
    monkeypatch.setattr(config, "RESEND_FROM_EMAIL", "")

    with pytest.raises(AppointmentNotificationError, match="not configured"):
        send_appointment_created_email(
            recipient_email="dietitian@example.com",
            dietitian_name="Avery Chen",
            client_name="Jordan Lee",
            client_email="jordan@example.com",
            appointment={},
        )
