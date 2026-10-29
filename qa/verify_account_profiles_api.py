"""Isolated profile API tests for all eight roles; no production credentials/DB."""
import io
import sys
import types
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "back-end"))
sys.modules["database"] = types.ModuleType("database")
sys.modules["config"] = types.SimpleNamespace(DATABASE_ENABLED=False)
from state import (
    users_db, admins_db, staff_accounts_db, account_profiles_db, profile_photos_db,
    admin_sessions_db, client_sessions_db, dietitian_sessions_db, staff_sessions_db,
)
from security import hash_password
from routers import account_profile

for store in (users_db, admins_db, staff_accounts_db, account_profiles_db, profile_photos_db,
              admin_sessions_db, client_sessions_db, dietitian_sessions_db, staff_sessions_db):
    store.clear()
roles = ["client", "dietitian", "admin", "reception", "branch_manager", "compliance_officer", "executive", "content_manager"]
for role in roles:
    user_id = f"user_{role}"
    user = {"id": user_id, "type": role, "role": role, "full_name": "Taylor Health", "email": f"{role}@test.local", "password_hash": hash_password("CurrentSecret123!"), "is_active": True}
    if role == "client":
        user.update(gender="female", id_number="dummy", dietitian_id="user_dietitian", phone_number="0821234567")
    target = admins_db if role == "admin" else users_db if role in ("client", "dietitian") else staff_accounts_db
    target[user_id] = user
    target_sessions = admin_sessions_db if role == "admin" else client_sessions_db if role == "client" else dietitian_sessions_db if role == "dietitian" else staff_sessions_db
    target_sessions[f"token_{role}"] = user_id
app = FastAPI()
app.include_router(account_profile.router)
api = TestClient(app)
headers = lambda role: {"Authorization": f"Bearer token_{role}"}
checks = 0

def expect(status, response):
    global checks
    assert response.status_code == status, (status, response.status_code, response.text)
    checks += 1
    return response

expect(401, api.get("/api/v1/account/me"))
expect(401, api.put("/api/v1/account/photo", files={"file": ("a.png", b"hello", "image/png")}))
for role in roles:
    record = expect(200, api.get("/api/v1/account/me", headers=headers(role))).json()
    assert record["id"] == f"user_{role}"
    assert record["email"] == f"{role}@test.local"
    saved = expect(200, api.put("/api/v1/account/me", json={
        "full_name": "Jamie Account", "phone_number": "+27 821234567", "address": "Limpopo",
        "bio": "Short professional introduction." if role != "client" else None,
        "emergency_contact": "Trusted contact" if role == "client" else None,
    }, headers=headers(role))).json()
    assert saved["full_name"] == "Jamie Account"
    assert saved["address"] == "Limpopo"
    assert saved["phone_number"] == "+27 821234567"
    expect(200, api.put("/api/v1/account/preferences", json={
        "preferred_contact": "phone", "email_notifications": False, "appointment_reminders": False,
    }, headers=headers(role)))
    updated = expect(200, api.get("/api/v1/account/me", headers=headers(role))).json()
    assert updated["preferred_contact"] == "phone" and not updated["email_notifications"]
    expect(404, api.get("/api/v1/account/photo", headers=headers(role)))

image = Image.new("RGB", (900, 480), "#4c8990")
buffer = io.BytesIO()
image.save(buffer, "PNG")
photo = buffer.getvalue()
for role in roles:
    expect(415, api.put("/api/v1/account/photo", headers=headers(role), files={"file": ("malware.svg", b"<svg />", "image/svg+xml")}))
    expect(415, api.put("/api/v1/account/photo", headers=headers(role), files={"file": ("fake.png", b"not image", "image/png")}))
    expect(413, api.put("/api/v1/account/photo", headers=headers(role), files={"file": ("large.png", b"x" * (2*1024*1024 + 1), "image/png")}))
    expect(200, api.put("/api/v1/account/photo", headers=headers(role), files={"file": ("photo.png", photo, "image/png")}))
    fetched = expect(200, api.get("/api/v1/account/photo", headers=headers(role)))
    assert fetched.headers["content-type"].startswith("image/webp")
    assert fetched.headers["cache-control"] == "private, no-store"
    with Image.open(io.BytesIO(fetched.content)) as loaded:
        assert loaded.size == (512, 512)
    expect(200, api.delete("/api/v1/account/photo", headers=headers(role)))
    expect(404, api.get("/api/v1/account/photo", headers=headers(role)))

# Old registration photo is still readable, but deleting a photo hides it.
profile_photos_db["user_client"] = {"bytes": photo, "content_type": "image/png"}
expect(404, api.get("/api/v1/account/photo", headers=headers("client")))
account_profiles_db[("client", "user_client")]["photo_hidden"] = False
expect(200, api.get("/api/v1/account/photo", headers=headers("client")))
assert api.get("/api/v1/account/me", headers=headers("client")).json()["has_photo"]
expect(200, api.delete("/api/v1/account/photo", headers=headers("client")))
expect(404, api.get("/api/v1/account/photo", headers=headers("client")))

# No one can retrieve another role's picture through this self-only endpoint.
expect(404, api.get("/api/v1/account/photo", headers=headers("dietitian")))
expect(422, api.put("/api/v1/account/me", json={"full_name": "J", "phone_number": "123"}, headers=headers("client")))
expect(422, api.put("/api/v1/account/preferences", json={"preferred_contact": "pigeon", "email_notifications": True, "appointment_reminders": True}, headers=headers("client")))
expect(400, api.post("/api/v1/account/password", json={"current_password": "wrong", "new_password": "LongNewPassword678!"}, headers=headers("client")))
for role in roles:
    expect(200, api.post("/api/v1/account/password", json={
        "current_password": "CurrentSecret123!", "new_password": "LongNewPassword678!",
    }, headers=headers(role)))
    expect(401, api.get("/api/v1/account/me", headers=headers(role)))
print(f"Account profiles: {checks} backend checks passed across all 8 user roles")
