"""FR-1.5 SMTP delivery state contract. Never sends network email."""
import os,sys,types
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
os.environ['APP_USE_IN_MEMORY_DB']='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'back-end'))
try:import database
except ImportError:sys.modules['database']=types.ModuleType('database')
import welcome_worker
sent=[]
class Cursor:
 def __init__(self):self.executed=[]
 def execute(self,q,p=None):self.executed.append((q,p))
 def fetchone(self):return {'message_id':'message-test','recipient_email':'example@example.test','recipient_name':'Example Patient','attempts':0}
rec=Cursor()
@contextmanager
def cursor():yield rec
with patch('welcome_worker.smtp_is_configured',return_value=False):
 assert welcome_worker.run_once() is False
assert not rec.executed
with patch('welcome_worker.smtp_is_configured',return_value=True),\
     patch('welcome_worker.database.cursor',side_effect=cursor,create=True),\
     patch('welcome_worker.send_welcome_email',side_effect=lambda email,name:sent.append((email,name))):
 assert welcome_worker.run_once() is True
assert sent==[('example@example.test','Example Patient')]
assert any('state=\'SENT\'' in q for q,_ in rec.executed)
rec2=Cursor()
@contextmanager
def cursor2():yield rec2
with patch('welcome_worker.smtp_is_configured',return_value=True),\
     patch('welcome_worker.database.cursor',side_effect=cursor2,create=True),\
     patch('welcome_worker.send_welcome_email',side_effect=RuntimeError('fake failure')):
 assert welcome_worker.run_once() is True
assert any('state=\'RETRY\'' in q for q,_ in rec2.executed)
print('PASS: unconfigured SMTP does not send; configured worker sends or schedules retries')
