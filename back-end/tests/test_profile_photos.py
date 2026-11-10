from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app
import config
import state
from onboarding_services import MAX_PHOTO_BYTES

api = TestClient(app.app)


@pytest.fixture(autouse=True)
def isolated_in_memory(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    for store in (
        state.admin_sessions_db,
        state.dietitian_sessions_db,
        state.client_sessions_db,
        state.staff_sessions_db,
        state.staff_accounts_db,
        state.profile_photos_db,
    ):
        store.clear()
    yield
    for store in (
        state.admin_sessions_db,
        state.dietitian_sessions_db,
        state.client_sessions_db,
        state.staff_sessions_db,
        state.staff_accounts_db,
        state.profile_photos_db,
    ):
        store.clear()


def png_image():
    output = BytesIO()
    Image.new("RGB", (2, 2), "green").save(output, format="PNG")
    return output.getvalue()


def auth_for(role, account_id):
    token = f"{role}-token"
    sessions = {
        "admin": state.admin_sessions_db,
        "dietitian": state.dietitian_sessions_db,
        "client": state.client_sessions_db,
    }.get(role, state.staff_sessions_db)
    sessions[token] = account_id
    if sessions is state.staff_sessions_db:
        state.staff_accounts_db[account_id] = {"role": role, "is_active": True}
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    "role",
    [
        "client",
        "dietitian",
        "admin",
        "reception",
        "branch_manager",
        "compliance_officer",
        "executive",
        "content_manager",
    ],
)
def test_each_account_role_can_upload_and_read_own_photo(role):
    headers = auth_for(role, "account-1")
    image = png_image()

    uploaded = api.put(
        "/api/v1/profile/photo",
        headers=headers,
        files={"file": ("profile.png", image, "image/png")},
    )

    assert uploaded.status_code == 200
    response = api.get("/api/v1/profile/photo", headers=headers)
    assert response.status_code == 200
    assert response.content == image
    assert response.headers["cache-control"] == "private, no-store"
    assert state.profile_photos_db[f"{role}:account-1"]["bytes"] == image


def test_photo_can_be_replaced_and_removed():
    headers = auth_for("client", "patient-1")
    first = png_image()
    second_output = BytesIO()
    Image.new("RGB", (3, 3), "blue").save(second_output, format="PNG")
    second = second_output.getvalue()

    assert api.put(
        "/api/v1/profile/photo",
        headers=headers,
        files={"file": ("first.png", first, "image/png")},
    ).status_code == 200
    assert api.put(
        "/api/v1/profile/photo",
        headers=headers,
        files={"file": ("second.png", second, "image/png")},
    ).status_code == 200
    assert api.get("/api/v1/profile/photo", headers=headers).content == second

    removed = api.delete("/api/v1/profile/photo", headers=headers)

    assert removed.status_code == 200
    assert api.get("/api/v1/profile/photo", headers=headers).status_code == 404


def test_photo_upload_requires_authentication_and_valid_image():
    image = png_image()
    unauthenticated = api.put(
        "/api/v1/profile/photo",
        files={"file": ("profile.png", image, "image/png")},
    )
    headers = auth_for("client", "patient-1")
    invalid_type = api.put(
        "/api/v1/profile/photo",
        headers=headers,
        files={"file": ("profile.gif", image, "image/gif")},
    )
    invalid_image = api.put(
        "/api/v1/profile/photo",
        headers=headers,
        files={"file": ("profile.png", b"\x89PNG\r\n\x1a\nnot-an-image", "image/png")},
    )
    oversized = api.put(
        "/api/v1/profile/photo",
        headers=headers,
        files={"file": ("profile.png", b"x" * (MAX_PHOTO_BYTES + 1), "image/png")},
    )

    assert unauthenticated.status_code == 401
    assert invalid_type.status_code == 422
    assert invalid_image.status_code == 422
    assert oversized.status_code == 422


def test_existing_client_registration_photo_is_available_to_self_service_api():
    headers = auth_for("client", "legacy-patient")
    image = png_image()
    state.profile_photos_db["legacy-patient"] = {
        "content_type": "image/png",
        "bytes": image,
    }

    response = api.get("/api/v1/profile/photo", headers=headers)

    assert response.status_code == 200
    assert response.content == image


def test_removing_client_photo_also_removes_legacy_registration_photo():
    headers = auth_for("client", "legacy-patient")
    state.profile_photos_db["legacy-patient"] = {
        "content_type": "image/png",
        "bytes": png_image(),
    }

    assert api.delete("/api/v1/profile/photo", headers=headers).status_code == 200
    assert api.get("/api/v1/profile/photo", headers=headers).status_code == 404


def test_profile_photo_endpoints_require_authentication():
    assert api.get("/api/v1/profile/photo").status_code == 401
    assert api.delete("/api/v1/profile/photo").status_code == 401
