"""Goal prescription and patient plan permissions, using only in-memory fixtures."""
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import state
from routers.appointments import router as appointments_router
from routers.meal_planning import router as meal_plan_router
from routers import meal_planning

app = FastAPI()
app.include_router(appointments_router)
app.include_router(meal_plan_router)
http = TestClient(app)

@pytest.fixture(autouse=True)
def safe_in_memory(monkeypatch):
    monkeypatch.setattr(config, 'DATABASE_ENABLED', False)
    for store in (state.users_db, state.goals_db, state.client_sessions_db, state.dietitian_sessions_db, state.admin_sessions_db):
        store.clear()
    meal_planning._draft_store.clear()
    state.users_db.update({
        'p1': {'id': 'p1', 'type': 'client', 'dietitian_id': 'd1'},
        'p2': {'id': 'p2', 'type': 'client', 'dietitian_id': 'd2'},
    })
    state.client_sessions_db.update({'patient-1':'p1', 'patient-2':'p2'})
    state.dietitian_sessions_db.update({'doctor-1':'d1', 'doctor-2':'d2'})
    state.admin_sessions_db['admin-1']='a1'
    yield
    for store in (state.users_db, state.goals_db, state.client_sessions_db, state.dietitian_sessions_db, state.admin_sessions_db):
        store.clear()
    meal_planning._draft_store.clear()


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def test_only_assigned_dietitian_can_prescribe_goal():
    item = {'client_id':'p1', 'target_metric':'Balanced meals per day', 'target_value':3}
    assert http.post('/api/v1/goals', json=item).status_code == 401
    assert http.post('/api/v1/goals', json=item, headers=auth('patient-1')).status_code == 403
    assert http.post('/api/v1/goals', json=item, headers=auth('patient-2')).status_code == 403
    assert http.post('/api/v1/goals', json=item, headers=auth('doctor-2')).status_code == 403
    assert http.post('/api/v1/goals', json=item, headers=auth('admin-1')).status_code == 403
    created = http.post('/api/v1/goals', json=item, headers=auth('doctor-1'))
    assert created.status_code == 200, created.text
    assert created.json()['goal']['target_metric'] == item['target_metric']
    listed = http.get('/api/v1/goals?client_id=p1', headers=auth('patient-1'))
    assert listed.status_code == 200
    assert listed.json()[0]['target_value'] == 3
    assert http.get('/api/v1/goals?client_id=p1', headers=auth('patient-2')).status_code == 403


def test_meal_plans_are_only_published_to_own_patient():
    meal_planning._draft_store['draft1'] = {
        'plan_id': 'draft1', 'client_id':'p1', 'dietitian_id':'d1',
        'status': 'PENDING_REVIEW', 'draft_json': {'diet_type':'Example', 'days':1},
        'approved_json': None, 'review_note': None, 'reviewed_at': None,
    }
    assert http.get('/api/v1/meal-plans/approved', headers=auth('patient-1')).json() == []
    assert http.get('/api/v1/meal-plans/approved', headers=auth('doctor-1')).status_code == 401
    assert http.get('/api/v1/meal-plans/approved').status_code == 401
    assert http.get('/api/v1/meal-plans/approved/draft1', headers=auth('patient-1')).status_code == 404
    meal_planning._draft_store['draft1']['status'] = 'APPROVED'
    meal_planning._draft_store['draft1']['approved_json'] = {'diet_type':'Example', 'days':1, 'schedule': []}
    assert len(http.get('/api/v1/meal-plans/approved', headers=auth('patient-1')).json()) == 1
    assert http.get('/api/v1/meal-plans/approved', headers=auth('patient-2')).json() == []
    assert http.get('/api/v1/meal-plans/approved/draft1', headers=auth('patient-2')).status_code == 404
