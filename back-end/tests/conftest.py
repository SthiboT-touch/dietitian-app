"""Never deliver email to external recipients during the test suite."""
import pytest
import resend
from ai_cache import response_cache


@pytest.fixture(autouse=True)
def isolate_mail_delivery(monkeypatch):
    monkeypatch.setattr(resend.Emails, "send", lambda *args, **kwargs: {"id": "test-email"})


@pytest.fixture(autouse=True)
def isolate_ai_response_cache():
    response_cache.clear()
    yield
    response_cache.clear()
