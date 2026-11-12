"""HPCSA review and clinical-access regressions; no mail or council calls."""
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient

import app
import config
import hpcsa_verification as hpcsa
import state
from routers import auth_admin
from schemas import DietitianRegister

api = TestClient(app.app)


def headers(token):
    return {"Authorization": "Bearer " + token}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    monkeypatch.setattr(hpcsa, "today", lambda: date(2026, 11, 11))
    stores = (state.users_db, state.branches_db, state.businesses_db,
              state.dietitian_documents_db, state.approval_log_db,
              state.dietitian_sessions_db, state.admin_sessions_db,
              state.verified_email_db, state.clients_db)
    for store in stores:
        store.clear()
    state.users_db["d"] = {"id": "d", "type": "dietitian", "full_name": "Legal Name",
                           "email": "legal@example.com", "license_number": "DT0012345",
                           "status": "PENDING", "branch_id": "b"}
    state.branches_db["b"] = {"branch_id": "b", "business_id": "biz", "business_name": "Practice",
                              "name": "Clinic", "address": "1 Main Street"}
    state.dietitian_sessions_db["doctor"] = "d"
    state.admin_sessions_db["admin"] = "a"
    yield
    for store in stores:
        store.clear()


def upload(expiry="2027-03-31"):
    return api.post("/api/v1/dietitians/me/documents", headers=headers("doctor"),
                    data={"practising_card_expires_at": expiry},
                    files={"file": ("card.pdf", b"%PDF-1.4\ncard", "application/pdf")})


def review(card_id, **overrides):
    payload = {"dietitian_id": "d", "status": "APPROVED", "hpcsa_register_checked": True,
               "practising_card_document_id": card_id}
    payload.update(overrides)
    return api.post("/api/v1/admin/approvals", json=payload, headers=headers("admin"))


@pytest.mark.parametrize("number", ["NT0012345", "RD-2048", "DT1234", "DT123456789", "DT１２３４５", "DT12345x"])
def test_invalid_registration_number(number):
    response = api.post("/api/v1/auth/register/dietitian", json={
        "first_name": "Legal", "last_name": "Name", "email": "other@example.com",
        "password": "safe-password", "license_number": number})
    assert response.status_code == 422


def test_normalization_and_duplicate_number(monkeypatch):
    model = DietitianRegister(first_name="Legal", last_name="Name", email="other@example.com",
                              password="safe-password", license_number=" dt 0012345 ")
    assert model.license_number == "DT0012345"
    monkeypatch.setattr(auth_admin, "_require_verified_registration_email", lambda email: {})
    assert api.post("/api/v1/auth/register/dietitian", json=model.model_dump()).status_code == 409


def test_review_enforces_admin_evidence_and_register_confirmation():
    card = upload().json()["document_id"]
    assert api.post("/api/v1/admin/approvals", headers=headers("doctor"),
                    json={"dietitian_id": "d", "status": "APPROVED"}).status_code == 401
    assert review(card, hpcsa_register_checked=False).status_code == 409
    assert review("nonexistent-card").status_code == 409
    state.dietitian_documents_db[card]["dietitian_id"] = "other"
    assert review(card).status_code == 409
    state.dietitian_documents_db[card]["dietitian_id"] = "d"
    assert review(card).status_code == 200
    assert state.users_db["d"]["hpcsa_verified_until"] == date(2027, 3, 31)
    audit = state.approval_log_db[-1]
    assert audit["admin_id"] == "a"
    assert audit["practising_card_document_id"] == card
    assert audit["hpcsa_register_checked"] is True


@pytest.mark.parametrize("expiry", ["2026-03-31", "2028-03-31", "2027-04-01"])
def test_card_must_cover_current_registration_year(expiry):
    assert upload(expiry).status_code == 422


def test_expiry_blocks_existing_session_and_keeps_renewal_available(monkeypatch):
    card = upload().json()["document_id"]
    assert api.get("/api/v1/dietitians").json() == []
    assert api.get("/api/v1/clients/dummy/care", headers=headers("doctor")).status_code == 403
    assert review(card).status_code == 200
    assert len(api.get("/api/v1/dietitians").json()) == 1
    assert api.get("/api/v1/clients?dietitian_id=d", headers=headers("doctor")).status_code == 200
    monkeypatch.setattr(hpcsa, "today", lambda: date(2027, 4, 1))
    assert api.get("/api/v1/clients/dummy/care", headers=headers("doctor")).status_code == 403
    assert api.get("/api/v1/dietitians").json() == []
    assert api.get("/api/v1/dietitians/me/approval", headers=headers("doctor")).json()["verification_current"] is False
    assert api.get("/api/v1/admin/approvals/pending", headers=headers("admin")).json()[0]["dietitian_id"] == "d"
    assert api.post("/api/v1/dietitians/me/approval/resubmit", headers=headers("doctor")).status_code == 200
    assert review(card).status_code == 409


def test_expiry_day_is_inclusive_and_rejection_revokes_access(monkeypatch):
    card = upload().json()["document_id"]
    assert review(card).status_code == 200
    monkeypatch.setattr(hpcsa, "today", lambda: date(2027, 3, 31))
    assert hpcsa.verification_is_current(state.users_db["d"])
    assert review(None, status="REJECTED", notes=" ").status_code == 422
    assert review(None, status="REJECTED", notes="Register shows suspension").status_code == 200
    assert not hpcsa.verification_is_current(state.users_db["d"])
    assert state.users_db["d"]["hpcsa_verified_until"] is None


def test_supporting_document_without_expiry_cannot_be_used_as_card():
    result = api.post("/api/v1/dietitians/me/documents", headers=headers("doctor"),
                      files={"file": ("identity.pdf", b"%PDF-1.4\nidentity", "application/pdf")})
    assert result.status_code == 201
    assert review(result.json()["document_id"]).status_code == 409


@pytest.mark.parametrize("status,expiry,allowed", [
    ("PENDING", date(2027, 3, 31), False),
    ("REJECTED", date(2027, 3, 31), False),
    ("APPROVED", None, False),
    ("APPROVED", date(2026, 3, 31), False),
    ("APPROVED", date(2027, 3, 31), True),
])
def test_postgres_clinical_guard_uses_authoritative_record(monkeypatch, status, expiry, allowed):
    class Cursor:
        def execute(self, sql, params):
            assert params == ("d",)
        def fetchone(self):
            return {"status": status, "hpcsa_verified_until": expiry}
    @contextmanager
    def cursor():
        yield Cursor()
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    monkeypatch.setattr(auth_admin.database, "cursor", cursor)
    if allowed:
        hpcsa.require_current_verification("Bearer doctor")
    else:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as error:
            hpcsa.require_current_verification("Bearer doctor")
        assert error.value.status_code == 403


def test_postgres_approval_persists_card_expiry_and_audit(monkeypatch):
    statements = []
    class Cursor:
        def execute(self, sql, params):
            self.sql = sql
            statements.append((sql, params))
        def fetchone(self):
            if "SELECT registration_number" in self.sql:
                return {"registration_number": "DT0012345"}
            if "FROM dietitian_document" in self.sql and "practising_card_expires_at" in self.sql:
                assert statements[-1][1] == ("card-1", "d")
                return {"practising_card_expires_at": date(2027, 3, 31)}
            if "SELECT b.name" in self.sql:
                return {"name": "Clinic", "address": "1 Main Street"}
            if "COUNT(*)" in self.sql:
                return {"document_count": 1}
            return {"dietitian_id": "d"}
    @contextmanager
    def cursor():
        yield Cursor()
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    monkeypatch.setattr(auth_admin.database, "cursor", cursor)
    assert review("card-1").status_code == 200
    update = next(params for sql, params in statements if sql.startswith("UPDATE dietitian"))
    assert update == ("APPROVED", date(2027, 3, 31), "d")
    audit = next(params for sql, params in statements if sql.startswith("INSERT INTO approval_log"))
    assert audit == ("a", "d", "APPROVED", None, "card-1", date(2027, 3, 31), True)


def test_every_clinical_router_has_current_verification_guard():
    from fastapi.routing import APIRoute
    from routers import clients, appointments, meal_planning, food_recipes, ai, care
    endpoints = {route.endpoint for router in (clients.router, appointments.router,
                 meal_planning.router, food_recipes.router, ai.router, care.router)
                 for route in router.routes if isinstance(route, APIRoute)}
    checked = 0
    effective_routes = []
    for route in app.app.routes:
        if hasattr(route, "effective_route_contexts"):
            effective_routes.extend(route.effective_route_contexts())
        else:
            effective_routes.append(route)
    for route in effective_routes:
        if getattr(route, "endpoint", None) in endpoints:
            assert any(dep.call is hpcsa.require_current_verification for dep in route.dependant.dependencies)
            checked += 1
    assert checked > 0


def test_corrections_require_own_session_and_reset_review():
    payload = {"first_name": "Correct Legal", "last_name": "Surname", "license_number": "dt 0076543"}
    url = "/api/v1/dietitians/me/registration"
    assert api.patch(url, json=payload).status_code == 401
    result = api.patch(url, json=payload, headers=headers("doctor"))
    assert result.status_code == 200
    assert state.users_db["d"]["license_number"] == "DT0076543"
    assert state.users_db["d"]["full_name"] == "Correct Legal Surname"
    state.users_db["other"] = {"id": "other", "type": "dietitian", "license_number": "DT0012345"}
    payload["license_number"] = "DT0012345"
    assert api.patch(url, json=payload, headers=headers("doctor")).status_code == 409
    state.users_db["d"].update(status="APPROVED", hpcsa_verified_until=date(2027, 3, 31))
    payload["license_number"] = "DT0076543"
    assert api.patch(url, json=payload, headers=headers("doctor")).status_code == 409


def test_pending_clinician_cannot_access_clinical_tools_but_can_upload():
    for path in ("/api/v1/clients?dietitian_id=d", "/api/v1/appointments?dietitian_id=d",
                 "/api/v1/ai/recommendations/pending", "/api/v1/meal-plans?dietitian_id=d"):
        assert api.get(path, headers=headers("doctor")).status_code == 403
    assert upload().status_code == 201


def test_private_card_download_requires_admin():
    document_id = upload().json()["document_id"]
    path = "/api/v1/admin/dietitian-documents/" + document_id
    assert api.get(path).status_code == 401
    assert api.get(path, headers=headers("doctor")).status_code == 401
    response = api.get(path, headers=headers("admin"))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"


def test_admin_can_inspect_new_registration_before_card_upload(monkeypatch):
    monkeypatch.setattr(auth_admin, "_require_verified_registration_email", lambda email: {})
    registered = api.post("/api/v1/auth/register/dietitian", json={
        "first_name": "New", "last_name": "Practitioner", "email": "new@example.com",
        "license_number": "DT0045678", "password": "safe-new-password"})
    assert registered.status_code == 200
    dietitian_id = registered.json()["user"]["id"]
    pending = api.get("/api/v1/admin/approvals/pending", headers=headers("admin")).json()
    assert any(item["dietitian_id"] == dietitian_id and item["documents"] == [] for item in pending)
    url = "/api/v1/admin/dietitians/" + dietitian_id
    assert api.get(url).status_code == 401
    assert api.get(url, headers=headers("doctor")).status_code == 401
    result = api.get(url, headers=headers("admin"))
    assert result.status_code == 200
    assert result.json()["full_name"] == "New Practitioner"
    assert result.json()["status"] == "PENDING"
    assert result.json()["documents"] == []
    assert result.json()["reviews"] == []
    assert "password" not in result.text
    assert api.get("/api/v1/admin/dietitians/missing", headers=headers("admin")).status_code == 404


def test_inspection_includes_private_document_metadata_and_review_history():
    card = upload().json()["document_id"]
    assert review(card).status_code == 200
    result = api.get("/api/v1/admin/dietitians/d", headers=headers("admin")).json()
    assert result["verification_current"] is True
    assert result["hpcsa_verified_until"] == "2027-03-31"
    assert result["documents"][0]["document_id"] == card
    assert "file_data" not in result["documents"][0]
    assert result["reviews"][0]["admin_id"] == "a"
    assert result["reviews"][0]["action"] == "APPROVED"
