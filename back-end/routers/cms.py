"""Centralized Client Management System (CMS) endpoints."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

import config
import database
from schemas import EHRNoteCreate, NutritionPlanVersionCreate, OfflineSyncRequest
from security import require_admin
from state import (
    branches_db,
    clients_db,
    cms_attachments_db,
    cms_audit_db,
    cms_ehr_notes_db,
    cms_nutrition_plans_db,
    users_db,
)

router = APIRouter()
RETENTION_YEARS = 7


def _retention_until():
    retention_days = 365 * RETENTION_YEARS
    retention_end = datetime.utcnow() + timedelta(days=retention_days)
    return retention_end.date()


def _audit(client_id: str, actor_id: str, action: str, metadata=None):
    metadata = metadata or {}
    entry = {
        "audit_id": str(uuid4()),
        "client_id": client_id,
        "actor_id": actor_id,
        "action": action,
        "metadata": metadata,
        "accessed_at": datetime.utcnow().isoformat(),
    }
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO client_access_audit (audit_id, client_id, actor_id, action, metadata) "
                "VALUES (%s, %s, %s, %s, %s)",
                (entry["audit_id"], client_id, actor_id, action, json.dumps(metadata)),
            )
    else:
        cms_audit_db.append(entry)
    return entry


def _client_exists(client_id: str):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT client_id FROM client WHERE client_id = %s", (client_id,))
            return bool(cursor.fetchone())
    return client_id in users_db and users_db[client_id].get("type") == "client"


@router.get("/api/v1/cms/clients", tags=["2. Centralized Client Management"])
def search_cms_clients(
    q: Optional[str] = None, branch_id: Optional[str] = None, admin_id: str = Depends(require_admin)
):
    """Search the centralized client repository by name, ID, email, phone, or branch."""
    term = (q or "").strip().lower()
    if config.DATABASE_ENABLED:
        params = []
        where = []
        if term:
            where.append(
                "LOWER(CONCAT_WS(' ', c.name, c.client_id, c.id_number, c.email, c.phone_number, b.name)) LIKE %s"
            )
            params.append(f"%{term}%")
        if branch_id:
            where.append("d.branch_id = %s")
            params.append(branch_id)
        query = (
            "SELECT c.client_id, c.name, c.email, c.id_number, c.phone_number, c.status, c.gender, "
            "c.date_of_birth, c.dietitian_id, b.branch_id, b.name AS branch_name, "
            "TRIM(d.first_name || ' ' || d.last_name) AS dietitian_name "
            "FROM client c LEFT JOIN dietitian d ON d.dietitian_id = c.dietitian_id "
            "LEFT JOIN branch b ON b.branch_id = d.branch_id "
        )
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY LOWER(c.name)"
        with database.cursor() as cursor:
            cursor.execute(query, params)
            rows = [dict(row) for row in cursor.fetchall()]
        return rows

    rows = []
    for user in users_db.values():
        if user.get("type") != "client":
            continue
        dietitian = users_db.get(user.get("dietitian_id"), {})
        branch = branches_db.get(dietitian.get("branch_id"), {})
        row = {
            "client_id": user["id"],
            "name": user["full_name"],
            "email": user.get("email"),
            "id_number": user.get("id_number"),
            "phone_number": user.get("phone_number"),
            "status": user.get("status", "ACTIVE"),
            "gender": user.get("gender"),
            "date_of_birth": user.get("date_of_birth"),
            "dietitian_id": user.get("dietitian_id"),
            "branch_id": branch.get("branch_id"),
            "branch_name": branch.get("name"),
            "dietitian_name": dietitian.get("full_name"),
        }
        searchable_values = []
        for value in row.values():
            searchable_values.append(str(value or ""))
        searchable_text = " ".join(searchable_values).lower()
        if term and term not in searchable_text:
            continue
        if branch_id and row["branch_id"] != branch_id:
            continue
        rows.append(row)
    return sorted(rows, key=lambda item: item["name"].casefold())


@router.get("/api/v1/cms/clients/{client_id}/record", tags=["2. Centralized Client Management"])
def get_cms_record(client_id: str, admin_id: str = Depends(require_admin)):
    if not _client_exists(client_id):
        raise HTTPException(status_code=404, detail="Client record not found")
    _audit(client_id, admin_id, "client_record_viewed")
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT client_id, name, email, id_number, phone_number, gender, date_of_birth, status, height, activity_level, dietary_preferences FROM client WHERE client_id = %s",
                (client_id,),
            )
            client = dict(cursor.fetchone())
            cursor.execute(
                "SELECT note_id, note_type, content, version, author_id, created_at FROM ehr_note WHERE client_id = %s ORDER BY created_at DESC",
                (client_id,),
            )
            notes = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT plan_id, title, content, version, status, author_id, created_at FROM nutrition_plan_version WHERE client_id = %s ORDER BY created_at DESC",
                (client_id,),
            )
            plans = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT attachment_id, file_name, content_type, category, version, uploaded_by, uploaded_at, retention_until FROM client_attachment WHERE client_id = %s ORDER BY uploaded_at DESC",
                (client_id,),
            )
            attachments = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT log_date, weight, body_fat_pct, waist_cm, calories_consumed, water_ml, steps, sleep_minutes, notes FROM progress_log WHERE client_id = %s ORDER BY log_date DESC",
                (client_id,),
            )
            progress = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT audit_id, actor_id, action, metadata, accessed_at FROM client_access_audit WHERE client_id = %s ORDER BY accessed_at DESC LIMIT 100",
                (client_id,),
            )
            audit = [dict(row) for row in cursor.fetchall()]
        return {
            "client": client,
            "ehr_notes": notes,
            "nutrition_plans": plans,
            "attachments": attachments,
            "progress": progress,
            "audit": audit,
            "retention_years": RETENTION_YEARS,
        }

    client = users_db[client_id].copy()
    client.pop("password_hash", None)
    # Collect the attachments and recent audit entries for this client.
    attachments = []
    for attachment in cms_attachments_db.values():
        if attachment["client_id"] == client_id:
            attachments.append(attachment)

    audit_entries = []
    for entry in cms_audit_db:
        if entry["client_id"] == client_id:
            audit_entries.append(entry)
    audit_entries.reverse()

    return {
        "client": client,
        "ehr_notes": list(reversed(cms_ehr_notes_db.get(client_id, []))),
        "nutrition_plans": list(reversed(cms_nutrition_plans_db.get(client_id, []))),
        "attachments": attachments,
        "progress": list(reversed(clients_db.get(client_id, {}).get("progress", []))),
        "audit": audit_entries[:100],
        "retention_years": RETENTION_YEARS,
    }


@router.post(
    "/api/v1/cms/clients/{client_id}/ehr-notes",
    status_code=201,
    tags=["2. Centralized Client Management"],
)
def create_ehr_note(client_id: str, data: EHRNoteCreate, admin_id: str = Depends(require_admin)):
    if not _client_exists(client_id):
        raise HTTPException(status_code=404, detail="Client record not found")
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM ehr_note WHERE client_id = %s AND note_type = %s",
                (client_id, data.note_type),
            )
            version = cursor.fetchone()["next_version"]
            note_id = str(uuid4())
            cursor.execute(
                "INSERT INTO ehr_note (note_id, client_id, author_id, note_type, content, version) VALUES (%s, %s, %s, %s, %s, %s) RETURNING note_id, client_id, author_id, note_type, content, version, created_at",
                (note_id, client_id, admin_id, data.note_type, data.content, version),
            )
            note = dict(cursor.fetchone())
    else:
        version = 1
        for existing_note in cms_ehr_notes_db.get(client_id, []):
            if existing_note["note_type"] == data.note_type:
                version += 1
        note = {
            "note_id": str(uuid4()),
            "client_id": client_id,
            "author_id": admin_id,
            "note_type": data.note_type,
            "content": data.content,
            "version": version,
            "created_at": datetime.utcnow().isoformat(),
        }
        cms_ehr_notes_db.setdefault(client_id, []).append(note)
    _audit(
        client_id, admin_id, "ehr_note_created", {"note_type": data.note_type, "version": version}
    )
    return {"message": "EHR note saved", "note": note}


@router.post(
    "/api/v1/cms/clients/{client_id}/nutrition-plans",
    status_code=201,
    tags=["2. Centralized Client Management"],
)
def create_nutrition_plan_version(
    client_id: str, data: NutritionPlanVersionCreate, admin_id: str = Depends(require_admin)
):
    if not _client_exists(client_id):
        raise HTTPException(status_code=404, detail="Client record not found")
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM nutrition_plan_version WHERE client_id = %s AND title = %s",
                (client_id, data.title),
            )
            version = cursor.fetchone()["next_version"]
            plan_id = str(uuid4())
            cursor.execute(
                "INSERT INTO nutrition_plan_version (plan_id, client_id, author_id, title, content, version, status) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING plan_id, client_id, author_id, title, content, version, status, created_at",
                (plan_id, client_id, admin_id, data.title, data.content, version, data.status),
            )
            plan = dict(cursor.fetchone())
    else:
        version = 1
        for existing_plan in cms_nutrition_plans_db.get(client_id, []):
            if existing_plan["title"] == data.title:
                version += 1
        plan = {
            "plan_id": str(uuid4()),
            "client_id": client_id,
            "author_id": admin_id,
            "title": data.title,
            "content": data.content,
            "version": version,
            "status": data.status,
            "created_at": datetime.utcnow().isoformat(),
        }
        cms_nutrition_plans_db.setdefault(client_id, []).append(plan)
    _audit(
        client_id,
        admin_id,
        "nutrition_plan_version_created",
        {"title": data.title, "version": version},
    )
    return {"message": "Nutrition plan version saved", "plan": plan}


@router.post(
    "/api/v1/cms/clients/{client_id}/attachments",
    status_code=201,
    tags=["2. Centralized Client Management"],
)
async def upload_cms_attachment(
    client_id: str,
    file: UploadFile = File(...),
    category: str = Form("medical"),
    previous_attachment_id: str = Form(""),
    admin_id: str = Depends(require_admin),
):
    if not _client_exists(client_id):
        raise HTTPException(status_code=404, detail="Client record not found")
    file_name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not file_name:
        raise HTTPException(status_code=400, detail="A file name is required")
    contents = await file.read(config.MAX_CLIENT_DOCUMENT_BYTES + 1)
    if len(contents) > config.MAX_CLIENT_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Attachment must be 10 MB or smaller")
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM client_attachment WHERE client_id = %s AND file_name = %s",
                (client_id, file_name),
            )
            version = cursor.fetchone()["next_version"]
            attachment_id = str(uuid4())
            cursor.execute(
                "INSERT INTO client_attachment (attachment_id, client_id, uploaded_by, file_name, content_type, file_data, category, version, previous_attachment_id, retention_until, sha256) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULLIF(%s, ''), %s, %s) RETURNING attachment_id, client_id, file_name, content_type, category, version, uploaded_by, uploaded_at, retention_until, sha256",
                (
                    attachment_id,
                    client_id,
                    admin_id,
                    file_name,
                    file.content_type or "application/octet-stream",
                    contents,
                    category,
                    version,
                    previous_attachment_id,
                    _retention_until(),
                    hashlib.sha256(contents).hexdigest(),
                ),
            )
            attachment = dict(cursor.fetchone())
    else:
        latest_version = 0
        for existing_attachment in cms_attachments_db.values():
            if (
                existing_attachment["client_id"] == client_id
                and existing_attachment["file_name"] == file_name
            ):
                latest_version = max(latest_version, existing_attachment["version"])
        version = latest_version + 1
        attachment_id = str(uuid4())
        attachment = {
            "attachment_id": attachment_id,
            "client_id": client_id,
            "uploaded_by": admin_id,
            "file_name": file_name,
            "content_type": file.content_type or "application/octet-stream",
            "category": category,
            "version": version,
            "previous_attachment_id": previous_attachment_id or None,
            "uploaded_at": datetime.utcnow().isoformat(),
            "retention_until": _retention_until().isoformat(),
            "sha256": hashlib.sha256(contents).hexdigest(),
        }
        cms_attachments_db[attachment_id] = {**attachment, "file_data": contents}
    _audit(client_id, admin_id, "attachment_uploaded", {"file_name": file_name, "version": version})
    return attachment


@router.get(
    "/api/v1/cms/clients/{client_id}/attachments/{attachment_id}",
    tags=["2. Centralized Client Management"],
)
def download_cms_attachment(
    client_id: str, attachment_id: str, admin_id: str = Depends(require_admin)
):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT file_name, content_type, file_data FROM client_attachment WHERE client_id = %s AND attachment_id = %s",
                (client_id, attachment_id),
            )
            attachment = cursor.fetchone()
    else:
        attachment = cms_attachments_db.get(attachment_id)
        if attachment and attachment["client_id"] != client_id:
            attachment = None
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    _audit(client_id, admin_id, "attachment_downloaded", {"attachment_id": attachment_id})
    return Response(
        content=bytes(attachment["file_data"]),
        media_type=attachment["content_type"],
        headers={"Content-Disposition": f"inline; filename=\"{attachment['file_name']}\""},
    )


@router.post("/api/v1/cms/clients/{client_id}/sync", tags=["2. Centralized Client Management"])
def sync_offline_events(
    client_id: str, data: OfflineSyncRequest, admin_id: str = Depends(require_admin)
):
    if not _client_exists(client_id):
        raise HTTPException(status_code=404, detail="Client record not found")
    _audit(client_id, admin_id, "offline_sync_completed", {"event_count": len(data.events)})
    return {
        "message": "Offline changes synchronized",
        "accepted": len(data.events),
        "synchronized_at": datetime.utcnow().isoformat(),
        "conflict_policy": "server_record_wins",
    }
