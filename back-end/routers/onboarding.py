"""FR-1.6 patient photos and FR-1.7 reception-scanned QR check-ins."""
import secrets
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
import config
import database
from onboarding_services import new_checkin_credential, checkin_hash, qr_svg
from role_management import require_roles
from security import current_identity, authorize_client_access
from state import profile_photos_db, checkin_credentials_db, checkin_events_db, staff_accounts_db, users_db

router = APIRouter(tags=['Digital Onboarding'])


@router.get('/api/v1/clients/{client_id}/profile-photo')
def get_profile_photo(client_id: str, authorization: Optional[str] = Header(default=None)):
    authorize_client_access(client_id, current_identity(authorization))
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute('SELECT content_type, file_data FROM client_profile_photo WHERE client_id=%s', (client_id,))
            image = cursor.fetchone()
    else:
        image = profile_photos_db.get(client_id)
    if not image:
        raise HTTPException(404, 'No profile photo uploaded')
    return Response(content=bytes(image['file_data'] if 'file_data' in image else image['bytes']),
                    media_type=image['content_type'],
                    headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post('/api/v1/clients/{client_id}/checkin-code')
def new_client_checkin_code(client_id: str, response: Response, authorization: Optional[str] = Header(default=None)):
    """Generate short-lived display credential (previous code is revoked).

    Only the actual client can issue their own code; a privileged admin may
    inspect records but cannot impersonate a patient at check-in.
    """
    role, account = current_identity(authorization)
    if role != 'client' or account != client_id:
        raise HTTPException(403, 'Only the patient can request their check-in code')
    response.headers['Cache-Control'] = 'no-store'
    token, digest = new_checkin_credential()
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute('INSERT INTO client_checkin_credential (client_id, token_hash) VALUES (%s,%s) '
                           'ON CONFLICT (client_id) DO UPDATE SET token_hash=EXCLUDED.token_hash, rotated_at=NOW(), expires_at=NOW()+INTERVAL \'10 minutes\'',
                           (client_id, digest))
    else:
        checkin_credentials_db[client_id] = {'token_hash': digest, 'expires_at': datetime.now(timezone.utc).timestamp() + 600}
    return {'client_id': client_id, 'qr_svg': qr_svg('NC1:' + token), 'checkin_code': 'NC1:' + token,
            'instructions': 'Show this code to reception within 10 minutes. Generating a new code revokes the old one.'}


class CheckinRequest(BaseModel):
    checkin_code: str = Field(..., min_length=20, max_length=200)


@router.post('/api/v1/reception/check-in', status_code=201)
def scan_checkin(data: CheckinRequest, identity=Depends(require_roles('reception', 'branch_manager'))):
    """Staff-only check-in; never derive a client ID from scanned text."""
    staff_role, staff_id = identity
    token = data.checkin_code.removeprefix('NC1:').strip()
    if len(token) < 32:
        raise HTTPException(422, 'Invalid check-in code')
    digest = checkin_hash(token)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute('SELECT branch_id, is_active FROM staff_account WHERE staff_id=%s', (staff_id,))
            staff = cursor.fetchone()
            if not staff or not staff['is_active'] or not staff['branch_id']:
                raise HTTPException(403, 'An active branch assignment is required')
            cursor.execute('SELECT client_id FROM client_checkin_credential WHERE token_hash=%s AND expires_at > NOW() FOR UPDATE', (digest,))
            credential = cursor.fetchone()
            if not credential:
                raise HTTPException(404, 'Invalid or expired check-in code')
            client_id = credential['client_id']
            cursor.execute('DELETE FROM client_checkin_credential WHERE client_id=%s', (client_id,))
            cursor.execute('INSERT INTO client_checkin_event (checkin_id, client_id, staff_id, branch_id) '
                           'VALUES (%s,%s,%s,%s)', (str(uuid4()), client_id, staff_id, staff['branch_id']))
    else:
        staff = staff_accounts_db.get(staff_id)
        if not staff or not staff.get('is_active') or not staff.get('branch_id'):
            raise HTTPException(403, 'An active branch assignment is required')
        client_id = next((cid for cid, details in checkin_credentials_db.items()
                          if secrets.compare_digest(details['token_hash'], digest) and details['expires_at'] > datetime.now(timezone.utc).timestamp()), None)
        if not client_id:
            raise HTTPException(404, 'Invalid or expired check-in code')
        checkin_credentials_db.pop(client_id, None)  # single-use QR credential
        checkin_events_db.append({'checkin_id': str(uuid4()), 'client_id': client_id,
                                  'staff_id': staff_id, 'branch_id': staff['branch_id'],
                                  'checked_in_at': datetime.now(timezone.utc)})
    return {'message': 'Patient checked in', 'client_id': client_id, 'branch_id': staff['branch_id']}
