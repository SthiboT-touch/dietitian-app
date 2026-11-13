"""Never deliver email to external recipients during the test suite."""
import pytest
import resend


@pytest.fixture(autouse=True)
def isolate_mail_delivery(monkeypatch):
    monkeypatch.setattr(resend.Emails, "send", lambda *args, **kwargs: {"id": "test-email"})
