"""FastAPI contract tests for the care-review workflow (no real DB / personal data)."""
from datetime import date, datetime, timedelta
from pathlib import Path
import importlib
import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "back-end"))
# Keep tests isolated from PostgreSQL and secrets in .env.
sys.modules["database"] = types.ModuleType("database")
sys.modules["config"] = types.SimpleNamespace(DATABASE_ENABLED=False)
from state import users_db, appointments_db, care_reviews_db, dietitian_sessions_db, client_sessions_db
from routers import care_reviews

for store in (users_db, appointments_db, care_reviews_db, dietitian_sessions_db, client_sessions_db):
    store.clear()

users_db.update({
    "client1": {"id": "client1", "type": "client", "dietitian_id": "doc1"},
    "client2": {"id": "client2", "type": "client", "dietitian_id": "doc2"},
})
dietitian_sessions_db.update({"d1token": "doc1", "d2token": "doc2"})
client_sessions_db.update({"c1token": "client1", "c2token": "client2"})
appointments_db.update({
    "past1": {"appointment_id": "past1", "client_id": "client1", "dietitian_id": "doc1",
              "status": "CONFIRMED", "appointment_date": (datetime.now()-timedelta(days=2)).isoformat(),
              "consultation_type": "IN_PERSON"},
    "future1": {"appointment_id": "future1", "client_id": "client1", "dietitian_id": "doc1",
              "status": "CONFIRMED", "appointment_date": (datetime.now()+timedelta(days=2)).isoformat()},
    "pending1": {"appointment_id": "pending1", "client_id": "client1", "dietitian_id": "doc1",
              "status": "PENDING", "appointment_date": (datetime.now()-timedelta(days=2)).isoformat()},
    "other1": {"appointment_id": "other1", "client_id": "client2", "dietitian_id": "doc2",
              "status": "CONFIRMED", "appointment_date": (datetime.now()-timedelta(days=2)).isoformat()},
})
app = FastAPI()
app.include_router(care_reviews.router)
client = TestClient(app)
headers = lambda token: {"Authorization": f"Bearer {token}"}
base = {"client_id": "client1", "appointment_id": "past1", "review_summary": "Clinical review completed after the visit.",
        "monitoring_plan": "Review recorded symptoms and check in at follow-up.", "decision": "FOLLOW_UP"}

def expect(expected, response):
    assert response.status_code == expected, f"expected {expected}: got {response.status_code} {response.text}"

expect(401, client.get('/api/v1/care-reviews?client_id=client1'))
expect(403, client.get('/api/v1/care-reviews?client_id=client2', headers=headers('c1token')))
expect(403, client.post('/api/v1/care-reviews', headers=headers('c1token'), json=base))
expect(403, client.post('/api/v1/care-reviews', headers=headers('d2token'), json=base))
expect(404, client.post('/api/v1/care-reviews', headers=headers('d1token'), json={**base,"appointment_id":"missing"}))
expect(409, client.post('/api/v1/care-reviews', headers=headers('d1token'), json={**base,"appointment_id":"pending1"}))
expect(409, client.post('/api/v1/care-reviews', headers=headers('d1token'), json={**base,"appointment_id":"future1"}))
expect(409, client.post('/api/v1/care-reviews', headers=headers('d1token'), json={**base,"appointment_id":"other1"}))
expect(422, client.post('/api/v1/care-reviews', headers=headers('d1token'), json={**base,"review_summary":"short"}))
expect(422, client.post('/api/v1/care-reviews', headers=headers('d1token'), json={**base,"next_review_date":"2020-01-01"}))
response = client.post('/api/v1/care-reviews', headers=headers('d1token'), json=base)
expect(201, response)
assert response.json()["review"]["dietitian_id"] == 'doc1'
assert response.json()["review"]["monitoring_plan"] == base["monitoring_plan"]
response = client.get('/api/v1/care-reviews?client_id=client1', headers=headers('c1token'))
expect(200, response)
assert len(response.json()) == 1
expect(200, client.get('/api/v1/care-reviews?client_id=client1', headers=headers('d1token')))
expect(403, client.get('/api/v1/care-reviews?client_id=client1', headers=headers('c2token')))
print('Care journey API: 14 authorization, validation and review tests passed')
