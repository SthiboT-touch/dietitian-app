"""FR-1.3/1.5: registration consent and welcome outbox in ONE transaction."""
import os,sys,types
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
os.environ['APP_USE_IN_MEMORY_DB']='1'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'back-end'))
try:import database
except ImportError:sys.modules['database']=types.ModuleType('database')
from fastapi import FastAPI
from fastapi.testclient import TestClient
import config
from routers.auth_admin import router
class RecordingCursor:
 def __init__(self,fail_consent=False):self.calls=[];self.fail_consent=fail_consent
 def execute(self,statement,values=None):
  self.calls.append((statement,values))
  if self.fail_consent and statement.startswith('INSERT INTO client_registration_consent'):
   raise RuntimeError('Simulated database write error')
 def fetchone(self):return None
records=RecordingCursor()
@contextmanager
def fake_cursor():yield records
app=FastAPI();app.include_router(router)
api=TestClient(app,client=('192.0.2.10',45678))
body={'first_name':'Test','last_name':'User','email':'new@example.test',
 'id_number':'9005140012345','phone':'0821234567','gender':'other',
 'date_of_birth':'1990-05-14','password':'password123',
 'consent_to_care':True,'privacy_notice_version':'2026-10-28-v1'}
with patch('routers.auth_admin.email_is_registered',return_value=False),patch('routers.auth_admin.database.cursor',side_effect=fake_cursor,create=True):
 config.DATABASE_ENABLED=True
 result=api.post('/api/v1/auth/register/client',json=body)
assert result.status_code==200,result.text
inserts=[(s,p) for s,p in records.calls if s.startswith('INSERT INTO')]
assert len(inserts)==3,records.calls
client=next(v for s,v in inserts if s.startswith('INSERT INTO client ('))
consent=next(v for s,v in inserts if s.startswith('INSERT INTO client_registration_consent'))
queue=next(v for s,v in inserts if s.startswith('INSERT INTO registration_welcome_outbox'))
assert consent[0]==client[0]==queue[1]
assert consent[1]=='2026-10-28-v1' and consent[2].tzinfo is not None
assert consent[3]=='192.0.2.10' and consent[4]=='SELF'
assert queue[2]=='new@example.test'
source=(ROOT/'back-end/routers/auth_admin.py').read_text().split('def _create_client(',1)[1].split('def admin_setup_available(',1)[0]
assert source.count('with database.cursor() as cursor:')==1
assert source.index('INSERT INTO client_registration_consent')>source.index('INSERT INTO client (')
for filename,needle in [('010_client_registration_consent.sql','client_registration_consent'),('011_registration_welcome_outbox.sql','registration_welcome_outbox')]:
 assert needle in (ROOT/'back-end/migrations'/filename).read_text()
print('PASS: client, consent and welcome outbox are within the same transaction')
failed=RecordingCursor(fail_consent=True)
@contextmanager
def failing():yield failed
with patch('routers.auth_admin.email_is_registered',return_value=False),patch('routers.auth_admin.database.cursor',side_effect=failing,create=True):
 bad=TestClient(app,client=('192.0.2.10',45678),raise_server_exceptions=False)
 response=bad.post('/api/v1/auth/register/client',json=body)
assert response.status_code==500
assert len([s for s,_ in failed.calls if s.startswith('INSERT INTO')])==2
print('PASS: failed consent storage cannot return registration success')
