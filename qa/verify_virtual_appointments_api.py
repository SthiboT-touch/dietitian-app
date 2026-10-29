"""Safe isolated appointment tests; no PostgreSQL or external video calls."""
import os
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

os.environ['APP_USE_IN_MEMORY_DB'] = '1'
os.environ['NUTRICARE_MEETING_BASE_URL'] = 'https://meet.jit.si'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'back-end'))
sys.modules['database'] = types.ModuleType('database')

from fastapi import FastAPI
from fastapi.testclient import TestClient
import config
import state
from routers.appointments import router as appointments_router
from routers.onboarding import router as onboarding_router

config.DATABASE_ENABLED = False
api_app = FastAPI()
api_app.include_router(appointments_router)
api_app.include_router(onboarding_router)
api = TestClient(api_app)

for store in (state.users_db, state.client_sessions_db, state.dietitian_sessions_db,
              state.admin_sessions_db, state.appointments_db, state.checkin_credentials_db):
    store.clear()
state.users_db['c1'] = {'id':'c1', 'type':'client', 'dietitian_id': 'd1'}
state.users_db['c2'] = {'id':'c2', 'type':'client', 'dietitian_id': 'd2'}
state.client_sessions_db.update({'client-one': 'c1', 'client-two': 'c2'})
state.dietitian_sessions_db.update({'dietitian-one': 'd1', 'dietitian-two': 'd2'})
state.admin_sessions_db.update({'admin-one': 'a1'})

def headers(token):
    return {'Authorization': 'Bearer ' + token}

def booking(mode):
    return {'client_id':'c1', 'dietitian_id':'d1',
            'appointment_date':(datetime.now() + timedelta(days=2)).isoformat(),
            'consultation_type': mode}

# Reject invalid appointment types at schema boundary.
assert api.post('/api/v1/appointments',json=booking('PHONE'),headers=headers('client-one')).status_code == 422
assert api.post('/api/v1/appointments',json=booking('VIRTUAL')).status_code == 401
assert api.post('/api/v1/appointments',json=booking('VIRTUAL'),headers=headers('client-two')).status_code == 403

r = api.post('/api/v1/appointments',json=booking('VIRTUAL'),headers=headers('client-one'))
assert r.status_code == 200, r.text
virtual_id = r.json()['appointment']['appointment_id']
assert r.json()['appointment']['consultation_type'] == 'VIRTUAL'
assert 'virtual_room_id' not in r.json()['appointment']
url = f'/api/v1/appointments/{virtual_id}/meeting'
assert api.get(url).status_code == 401
assert api.get(url,headers=headers('client-one')).status_code == 409
assert api.get(url,headers=headers('client-two')).status_code == 403
assert api.get(url,headers=headers('dietitian-two')).status_code == 403
assert api.get(url,headers=headers('admin-one')).status_code == 403
assert api.get(f'/api/v1/appointments/{virtual_id}/meeting',headers=headers('dietitian-one')).status_code == 409

assert api.patch(f'/api/v1/appointments/{virtual_id}',json={'action':'APPROVED'},headers=headers('client-one')).status_code == 403
assert api.patch(f'/api/v1/appointments/{virtual_id}',json={'action':'APPROVED'},headers=headers('dietitian-one')).status_code == 200
room = api.get(url,headers=headers('client-one'))
assert room.status_code == 200, room.text
assert room.headers['cache-control'] == 'private, no-store'
room_url = room.json()['meeting_url']
assert room_url.startswith('https://meet.jit.si/nc-')
assert 'c1' not in room_url and 'd1' not in room_url
assert api.get(url,headers=headers('dietitian-one')).json()['meeting_url'] == room_url
assert 'virtual_room_id' not in str(api.get('/api/v1/appointments',headers=headers('client-one')).json())

# Virtual consultations are not eligible for reception QR check-in.
assert api.get('/api/v1/clients/c1/checkin-appointments',headers=headers('client-one')).json() == []
assert api.post('/api/v1/clients/c1/checkin-code',json={'appointment_id':virtual_id},headers=headers('client-one')).status_code == 409

# Legacy API clients default to in-person.
legacy = booking('IN_PERSON')
legacy.pop('consultation_type')
r=api.post('/api/v1/appointments',json=legacy,headers=headers('client-one'))
assert r.status_code == 200 and r.json()['appointment']['consultation_type'] == 'IN_PERSON'
inperson_id = r.json()['appointment']['appointment_id']
assert api.get(f'/api/v1/appointments/{inperson_id}/meeting',headers=headers('client-one')).status_code == 409
assert api.patch(f'/api/v1/appointments/{inperson_id}',json={'action':'APPROVED'},headers=headers('dietitian-one')).status_code == 200
assert [a['appointment_id'] for a in api.get('/api/v1/clients/c1/checkin-appointments',headers=headers('client-one')).json()] == [inperson_id]

# Cancellation revokes access through the NutriCare API.
assert api.patch(f'/api/v1/appointments/{virtual_id}',json={'action':'CANCELLED'},headers=headers('client-one')).status_code == 200
assert api.get(url,headers=headers('client-one')).status_code == 409
# Explicit failure instead of guessing a public meeting URL in production.
prev=os.environ['NUTRICARE_MEETING_BASE_URL']
os.environ['NUTRICARE_MEETING_BASE_URL']=''
new = api.post('/api/v1/appointments',json=booking('VIRTUAL'),headers=headers('client-one')).json()['appointment']['appointment_id']
assert api.patch(f'/api/v1/appointments/{new}',json={'action':'APPROVED'},headers=headers('dietitian-one')).status_code == 200
assert api.get(f'/api/v1/appointments/{new}/meeting',headers=headers('client-one')).status_code == 503
os.environ['NUTRICARE_MEETING_BASE_URL']=prev
print('PASS: type validation, 2 appointment modes, role controls, approval, meeting links, QR isolation, cancellation, provider requirement')
