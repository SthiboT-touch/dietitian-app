"""Client.py"""
"""2. Patient health history and 3. clinical labs and daily progress."""
import json
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from typing import Optional
from datetime import date, datetime
from uuid import uuid4
import database
import config
from state import users_db, clients_db, client_documents_db
from schemas import (
    PregnancyLog, LactationLog, AllergyEntry, MedicalConditionEntry, MetricLog, ProgressLog,
    LactationStatusEntry, DailyFeedingLog, MilkSupplyLog, WeaningLog,
    MaternalDiscomfortLog, InfantSensitivityLog, MealLog,
)
from lactation_guidance import (
    INCREASE_MILK_GUIDANCE, OVERSUPPLY_GUIDANCE, DISCOMFORT_SELF_CARE,
    weaning_guidance, discomfort_red_flags, infant_red_flags, daily_feeding_observations,
)
from helpers import fetch_client_profile
from security import (current_identity, authorize_client_access,
                      require_client_record_access)


router = APIRouter()


# --- 2. PATIENT HEALTH, LIFE STAGE & CLINICAL HISTORY ---

@router.get("/api/v1/clients", tags=["2. Patient Health & History"])
def list_clients(
    dietitian_id: Optional[str] = None,
    client_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    role, account_id = identity = current_identity(authorization)
    if client_id:
        authorize_client_access(client_id, identity)
    elif dietitian_id:
        if role not in {"admin", "dietitian"} or (role == "dietitian" and dietitian_id != account_id):
            raise HTTPException(status_code=403, detail="Not authorized to list these clients")
    elif role != "admin":
        return []

    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            if client_id:
                cursor.execute(
                    "SELECT client_id AS id, name, email, dietitian_id, status, id_number, date_of_birth, "
                    "gender, height, activity_level, dietary_preferences "
                    "FROM client WHERE client_id = %s",
                    (client_id,),
                )
            elif dietitian_id:
                cursor.execute(
                    "SELECT client_id AS id, name, dietitian_id, status FROM client "
                    "WHERE dietitian_id = %s ORDER BY LOWER(name)",
                    (dietitian_id,),
                )
            else:
                return []
            return [dict(row) for row in cursor.fetchall()]
    clients = [user for user in users_db.values() if user.get("type") == "client"]
    if client_id:
        clients = [user for user in clients if user["id"] == client_id]
    elif dietitian_id:
        clients = [user for user in clients if user.get("dietitian_id") == dietitian_id]
    else:
        return []
    return [
        {
            "id": user["id"],
            "name": user["full_name"],
            "dietitian_id": user.get("dietitian_id"),
            "status": "ACTIVE",
            **({
                "email": user.get("email"),
                "id_number": user.get("id_number"),
                "date_of_birth": user.get("date_of_birth"),
                "gender": user.get("gender"),
                "height": user.get("height"),
                "activity_level": user.get("activity_level"),
                "dietary_preferences": user.get("dietary_preferences"),
            } if client_id else {}),
        }
        for user in sorted(clients, key=lambda item: item["full_name"].casefold())
    ]


@router.get("/api/v1/clients/{client_id}/profile", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def get_client_profile(client_id: str):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            return fetch_client_profile(cursor, client_id)
    if client_id not in clients_db:
        clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    return clients_db[client_id]

@router.post("/api/v1/clients/{client_id}/pregnancy", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def log_pregnancy(client_id: str, data: PregnancyLog):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO pregnancy_profile (client_id, due_date, notes) VALUES (%s, %s, %s)",
                (client_id, data.due_date, json.dumps({"trimester": data.trimester})),
            )
        return {"message": "Pregnancy parameters updated", "data": data.model_dump()}
    if client_id not in clients_db:
        clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    clients_db[client_id]["pregnancy"] = data.model_dump()
    return {"message": "Pregnancy parameters updated", "data": clients_db[client_id]["pregnancy"]}

@router.post("/api/v1/clients/{client_id}/lactation", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def log_lactation(client_id: str, data: LactationLog):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT client_id FROM client WHERE client_id = %s", (client_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Patient record not found")
            cursor.execute(
                "UPDATE lactation_profile SET end_date = CURRENT_DATE "
                "WHERE client_id = %s AND end_date IS NULL",
                (client_id,),
            )
            if data.is_active:
                cursor.execute(
                    "INSERT INTO lactation_profile (client_id, start_date, notes) VALUES (%s, CURRENT_DATE, %s)",
                    (client_id, data.notes),
                )
        return {"message": "Lactation state updated", "data": data.model_dump()}
    if client_id not in clients_db:
        clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    clients_db[client_id]["lactation"] = data.model_dump()
    return {"message": "Lactation state updated", "data": clients_db[client_id]["lactation"]}
# --- LACTATION TRACKING (status, feeding, supply, weaning, discomfort, infant sensitivities) ---

LACTATION_LOGS = {
    "status": ("lactation_status_log", "logged_at DESC"),
    "daily-feeding": ("daily_feeding_log", "feed_date DESC, logged_at DESC"),
    "milk-supply": ("milk_supply_log", "log_date DESC, logged_at DESC"),
    "weaning": ("weaning_plan_log", "start_date DESC, logged_at DESC"),
    "maternal-discomfort": ("maternal_discomfort_log", "log_date DESC, logged_at DESC"),
    "infant-sensitivities": ("infant_sensitivity_log", "log_date DESC, logged_at DESC"),
}
LACTATION_DATE_FIELDS = {
    "daily-feeding": "feed_date",
    "milk-supply": "log_date",
    "weaning": "start_date",
    "maternal-discomfort": "log_date",
    "infant-sensitivities": "log_date",
}

def save_lactation_entry(client_id: str, kind: str, data):
    table, _ = LACTATION_LOGS[kind]
    values = data.model_dump()
    date_field = LACTATION_DATE_FIELDS.get(kind)
    if date_field and not values.get(date_field):
        values[date_field] = date.today()
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT client_id FROM client WHERE client_id = %s", (client_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Patient record not found")
            columns = ["log_id", "client_id", *values.keys()]
            params = [str(uuid4()), client_id, *values.values()]
            cursor.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) RETURNING *",
                params,
            )
            return dict(cursor.fetchone())
    if client_id not in clients_db:
        clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    entry = {"log_id": str(uuid4()), "client_id": client_id, **values, "logged_at": datetime.now().isoformat()}
    clients_db[client_id].setdefault("lactation_tracking", {}).setdefault(kind, []).append(entry)
    return entry

def list_lactation_entries(client_id: str, kind: str):
    table, order = LACTATION_LOGS[kind]
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT client_id FROM client WHERE client_id = %s", (client_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Patient record not found")
            cursor.execute(f"SELECT * FROM {table} WHERE client_id = %s ORDER BY {order}", (client_id,))
            return [dict(row) for row in cursor.fetchall()]
    if client_id not in clients_db:
        raise HTTPException(status_code=404, detail="Patient record not found")
    return list(reversed(clients_db[client_id].get("lactation_tracking", {}).get(kind, [])))

@router.post("/api/v1/clients/{client_id}/lactation/status", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def log_lactation_status(client_id: str, data: LactationStatusEntry):
    if data.infant_age_months is None and data.infant_birth_date:
        today = date.today()
        months = (today.year - data.infant_birth_date.year) * 12 + today.month - data.infant_birth_date.month
        if today.day < data.infant_birth_date.day:
            months -= 1
        data.infant_age_months = max(months, 0)
    return {"message": "Lactation status saved", "record": save_lactation_entry(client_id, "status", data)}

@router.get("/api/v1/clients/{client_id}/lactation/status", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def get_lactation_status(client_id: str):
    return list_lactation_entries(client_id, "status")

@router.post("/api/v1/clients/{client_id}/lactation/daily-feeding", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def log_daily_feeding(client_id: str, data: DailyFeedingLog):
    record = save_lactation_entry(client_id, "daily-feeding", data)
    return {"message": "Daily feeding saved", "record": record, "observations": daily_feeding_observations(record)}

@router.get("/api/v1/clients/{client_id}/lactation/daily-feeding", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def get_daily_feeding(client_id: str):
    return list_lactation_entries(client_id, "daily-feeding")

@router.post("/api/v1/clients/{client_id}/lactation/milk-supply", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def log_milk_supply(client_id: str, data: MilkSupplyLog):
    guidance = INCREASE_MILK_GUIDANCE if data.concern == "low_supply" else OVERSUPPLY_GUIDANCE
    return {"message": "Milk supply entry saved", "record": save_lactation_entry(client_id, "milk-supply", data), "guidance": guidance}

@router.get("/api/v1/clients/{client_id}/lactation/milk-supply", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def get_milk_supply(client_id: str):
    return list_lactation_entries(client_id, "milk-supply")

@router.get("/api/v1/lactation/guidance/increase-milk-production", tags=["2. Patient Health & History"])
def guidance_increase_milk_production():
    return INCREASE_MILK_GUIDANCE

@router.get("/api/v1/lactation/guidance/manage-oversupply", tags=["2. Patient Health & History"])
def guidance_manage_oversupply():
    return OVERSUPPLY_GUIDANCE

@router.get("/api/v1/lactation/guidance/weaning-nutrition", tags=["2. Patient Health & History"])
def guidance_weaning_nutrition(current_sessions: int = 6, target_sessions: int = 0, approach: str = "gradual"):
    if approach not in ("gradual", "partial", "abrupt_medical"):
        raise HTTPException(status_code=422, detail="approach must be gradual, partial or abrupt_medical")
    return weaning_guidance(current_sessions, target_sessions, approach)

@router.post("/api/v1/clients/{client_id}/lactation/weaning", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def log_weaning_plan(client_id: str, data: WeaningLog):
    record = save_lactation_entry(client_id, "weaning", data)
    return {
        "message": "Weaning plan saved",
        "record": record,
        "guidance": weaning_guidance(data.feeds_per_day_current, data.feeds_per_day_target, data.approach),
    }

@router.get("/api/v1/clients/{client_id}/lactation/weaning", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def get_weaning_plans(client_id: str):
    return list_lactation_entries(client_id, "weaning")

@router.post("/api/v1/clients/{client_id}/lactation/maternal-discomfort", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def log_maternal_discomfort(client_id: str, data: MaternalDiscomfortLog):
    flags = discomfort_red_flags(data)
    return {
        "message": "Maternal discomfort entry saved",
        "record": save_lactation_entry(client_id, "maternal-discomfort", data),
        "self_care": DISCOMFORT_SELF_CARE.get(data.symptom_type, []),
        "red_flags": flags,
        "seek_medical_care": bool(flags),
    }

@router.get("/api/v1/clients/{client_id}/lactation/maternal-discomfort", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def get_maternal_discomfort(client_id: str):
    return list_lactation_entries(client_id, "maternal-discomfort")

@router.post("/api/v1/clients/{client_id}/lactation/infant-sensitivities", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def log_infant_sensitivity(client_id: str, data: InfantSensitivityLog):
    flags = infant_red_flags(data)
    return {
        "message": "Infant sensitivity entry saved",
        "record": save_lactation_entry(client_id, "infant-sensitivities", data),
        "red_flags": flags,
        "seek_medical_care": bool(flags),
    }

@router.get("/api/v1/clients/{client_id}/lactation/infant-sensitivities", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def get_infant_sensitivities(client_id: str):
    return list_lactation_entries(client_id, "infant-sensitivities")

@router.get("/api/v1/clients/{client_id}/lactation/overview", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def get_lactation_overview(client_id: str):
    entries = {kind: list_lactation_entries(client_id, kind) for kind in LACTATION_LOGS}
    counts = {}
    for entry in entries["infant-sensitivities"]:
        trigger = (entry.get("suspected_trigger") or "").strip().lower()
        if trigger:
            counts[trigger] = counts.get(trigger, 0) + 1
    entries["recurring_triggers"] = sorted((name for name, total in counts.items() if total >= 2), key=lambda name: -counts[name])
    return entries

@router.post("/api/v1/clients/{client_id}/allergies", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def add_allergy(client_id: str, data: AllergyEntry):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO allergen (name) VALUES (%s) ON CONFLICT (name) DO UPDATE "
                "SET name = EXCLUDED.name RETURNING allergen_id",
                (data.allergen.strip(),),
            )
            allergen_id = cursor.fetchone()["allergen_id"]
            cursor.execute(
                "INSERT INTO client_allergy (client_id, allergen_id, severity) VALUES (%s, %s, %s) "
                "ON CONFLICT (client_id, allergen_id) DO UPDATE SET severity = EXCLUDED.severity",
                (client_id, allergen_id, data.severity.upper()),
            )
            profile = fetch_client_profile(cursor, client_id)
        return {"message": "Allergy mapped successfully", "allergies": profile["allergies"]}
    if client_id not in clients_db:
        clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    clients_db[client_id]["allergies"].append(data.model_dump())
    return {"message": "Allergy mapped successfully", "allergies": clients_db[client_id]["allergies"]}

@router.post("/api/v1/clients/{client_id}/medical-conditions", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def add_medical_condition(client_id: str, data: MedicalConditionEntry):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO medical_condition (name, icd_code) VALUES (%s, %s) "
                "ON CONFLICT (name) DO UPDATE SET icd_code = COALESCE(EXCLUDED.icd_code, medical_condition.icd_code) "
                "RETURNING condition_id",
                (data.condition_name.strip(), data.icd_code),
            )
            condition_id = cursor.fetchone()["condition_id"]
            cursor.execute(
                "INSERT INTO client_medical_condition (client_id, condition_id) VALUES (%s, %s) "
                "ON CONFLICT (client_id, condition_id) DO NOTHING",
                (client_id, condition_id),
            )
            profile = fetch_client_profile(cursor, client_id)
        return {"message": "Medical condition added", "conditions": profile["conditions"]}
    if client_id not in clients_db:
        clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    clients_db[client_id]["conditions"].append(data.model_dump())
    return {"message": "Medical condition added", "conditions": clients_db[client_id]["conditions"]}


# --- 3. CLINICAL LABS & DAILY PROGRESS LOGS ---

@router.post("/api/v1/clients/{client_id}/metrics", dependencies=[Depends(require_client_record_access)], tags=["3. Clinical Labs & Progress"])
def log_metric(client_id: str, data: MetricLog):
    if config.DATABASE_ENABLED:
        try:
            value = float(data.value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Metric value must be numeric") from exc
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO metric_type (name, unit) VALUES (%s, %s) "
                "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING metric_type_id",
                (data.metric_type.strip(), "unspecified"),
            )
            metric_type_id = cursor.fetchone()["metric_type_id"]
            cursor.execute(
                "INSERT INTO client_metric_log (client_id, metric_type_id, value) VALUES (%s, %s, %s)",
                (client_id, metric_type_id, value),
            )
            cursor.execute(
                "SELECT mt.name AS metric_type, cml.value FROM client_metric_log cml "
                "JOIN metric_type mt ON mt.metric_type_id = cml.metric_type_id "
                "WHERE cml.client_id = %s ORDER BY cml.recorded_at",
                (client_id,),
            )
            metrics = [{"metric_type": row["metric_type"], "value": str(row["value"])} for row in cursor.fetchall()]
        return {"message": "Metric logged successfully", "metrics": metrics}
    if client_id not in clients_db:
        clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    clients_db[client_id]["metrics"].append(data.model_dump())
    return {"message": "Metric logged successfully", "metrics": clients_db[client_id]["metrics"]}

@router.get("/api/v1/clients/{client_id}/metrics", dependencies=[Depends(require_client_record_access)], tags=["3. Clinical Labs & Progress"])
def get_metrics(client_id: str):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT client_id FROM client WHERE client_id = %s", (client_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Patient record not found")
            cursor.execute(
                "SELECT mt.name AS metric_type, cml.value FROM client_metric_log cml "
                "JOIN metric_type mt ON mt.metric_type_id = cml.metric_type_id "
                "WHERE cml.client_id = %s ORDER BY cml.recorded_at",
                (client_id,),
            )
            return [{"metric_type": row["metric_type"], "value": str(row["value"])} for row in cursor.fetchall()]
    if client_id not in clients_db:
        raise HTTPException(status_code=404, detail="Patient record not found")
    return clients_db[client_id].get("metrics", [])

@router.post("/api/v1/clients/{client_id}/progress", dependencies=[Depends(require_client_record_access)], tags=["3. Clinical Labs & Progress"])
def log_progress(client_id: str, data: ProgressLog):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO progress_log "
                "(client_id, log_date, weight, body_fat_pct, waist_cm, calories_consumed, water_ml, steps, sleep_minutes) "
                "VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (client_id, log_date) DO UPDATE SET "
                "weight = COALESCE(EXCLUDED.weight, progress_log.weight), "
                "body_fat_pct = COALESCE(EXCLUDED.body_fat_pct, progress_log.body_fat_pct), "
                "waist_cm = COALESCE(EXCLUDED.waist_cm, progress_log.waist_cm), "
                "calories_consumed = COALESCE(EXCLUDED.calories_consumed, progress_log.calories_consumed), "
                "water_ml = COALESCE(EXCLUDED.water_ml, progress_log.water_ml), "
                "steps = COALESCE(EXCLUDED.steps, progress_log.steps), "
                "sleep_minutes = COALESCE(EXCLUDED.sleep_minutes, progress_log.sleep_minutes)",
                (
                    client_id,
                    data.weight_kg,
                    data.body_fat_pct,
                    data.waist_cm,
                    data.calories,
                    data.water_ml,
                    data.steps,
                    round(data.sleep_hours * 60) if data.sleep_hours is not None else None,
                ),
            )
            cursor.execute(
                "SELECT log_date, weight AS weight_kg, body_fat_pct, waist_cm, calories_consumed AS calories, "
                "water_ml, steps, sleep_minutes / 60.0 AS sleep_hours FROM progress_log "
                "WHERE client_id = %s ORDER BY log_date",
                (client_id,),
            )
            progress = [
                {**dict(item), "log_date": item["log_date"].isoformat()}
                for item in cursor.fetchall()
            ]
        return {"message": "Progress entry saved", "progress": progress}
    if client_id not in clients_db:
        clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    log_date = date.today().isoformat()
    progress = clients_db[client_id]["progress"]
    existing_entry = next((entry for entry in progress if entry.get("log_date") == log_date), None)
    values = {key: value for key, value in data.model_dump().items() if value is not None}
    if existing_entry:
        existing_entry.update(values)
    else:
        progress.append({**values, "log_date": log_date})
    return {"message": "Progress entry saved", "progress": progress}

@router.get("/api/v1/clients/{client_id}/progress", dependencies=[Depends(require_client_record_access)], tags=["3. Clinical Labs & Progress"])
def get_progress(client_id: str):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT client_id FROM client WHERE client_id = %s", (client_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Patient record not found")
            cursor.execute(
                "SELECT log_date, weight AS weight_kg, body_fat_pct, waist_cm, "
                "calories_consumed AS calories, water_ml, steps, "
                "sleep_minutes / 60.0 AS sleep_hours FROM progress_log "
                "WHERE client_id = %s ORDER BY log_date",
                (client_id,),
            )
            return [
                {**dict(row), "log_date": row["log_date"].isoformat()}
                for row in cursor.fetchall()
            ]
    if client_id not in clients_db:
        raise HTTPException(status_code=404, detail="Patient record not found")
    return clients_db[client_id].get("progress", [])

@router.post("/api/v1/clients/{client_id}/meals", dependencies=[Depends(require_client_record_access)], tags=["3. Clinical Labs & Progress"])
def log_meal(client_id: str, data: MealLog):
    values = data.model_dump()
    values["log_date"] = (data.log_date or date.today()).isoformat()
    values["meal_log_id"] = str(uuid4())
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO meal_log (meal_log_id, client_id, log_date, meal_time, meal_type, description, calories, notes) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (values["meal_log_id"], client_id, values["log_date"], values["meal_time"], values["meal_type"], values["description"], values["calories"], values["notes"]),
            )
            return {"message": "Meal saved", "meal": values}
    if client_id not in clients_db:
        clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    clients_db[client_id].setdefault("meals", []).append({"client_id": client_id, **values})
    return {"message": "Meal saved", "meal": values}

@router.get("/api/v1/clients/{client_id}/meals", dependencies=[Depends(require_client_record_access)], tags=["3. Clinical Labs & Progress"])
def get_meals(client_id: str):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT meal_log_id, log_date, meal_time, meal_type, description, calories, notes "
                "FROM meal_log WHERE client_id = %s ORDER BY log_date DESC, meal_time DESC, created_at DESC",
                (client_id,),
            )
            return [dict(row) for row in cursor.fetchall()]
    if client_id not in clients_db:
        raise HTTPException(status_code=404, detail="Patient record not found")
    return list(reversed(clients_db[client_id].get("meals", [])))

@router.post("/api/v1/clients/{client_id}/medical-documents", status_code=201, dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
async def upload_medical_document(
    client_id: str,
    file: UploadFile = File(...),
    condition_name: str = Form(""),
    doctor_name: str = Form(""),
    doctor_information: str = Form(""),
):
    file_name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    content_type = file.content_type or "application/octet-stream"
    if not file_name or content_type not in {"application/pdf", "image/jpeg", "image/png"}:
        raise HTTPException(status_code=400, detail="Upload a PDF, JPEG, or PNG document")
    if not condition_name.strip() or not doctor_name.strip() or not doctor_information.strip():
        raise HTTPException(status_code=422, detail="Condition and doctor information are required")
    contents = await file.read(config.MAX_CLIENT_DOCUMENT_BYTES + 1)
    if len(contents) > config.MAX_CLIENT_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Document must be 10 MB or smaller")
    document_id = str(uuid4())
    metadata = {"document_id": document_id, "client_id": client_id, "file_name": file_name, "content_type": content_type, "condition_name": condition_name, "doctor_name": doctor_name, "doctor_information": doctor_information, "uploaded_at": datetime.now().isoformat()}
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO client_medical_document (document_id, client_id, file_name, content_type, file_data, condition_name, doctor_name, doctor_information) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (document_id, client_id, file_name, content_type, contents, condition_name, doctor_name, doctor_information),
            )
    else:
        client_documents_db[document_id] = {**metadata, "file_data": contents}
    return metadata

@router.get("/api/v1/clients/{client_id}/medical-documents", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def list_medical_documents(client_id: str):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT document_id, client_id, file_name, content_type, condition_name, doctor_name, doctor_information, uploaded_at "
                "FROM client_medical_document WHERE client_id = %s ORDER BY uploaded_at DESC", (client_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    return [{key: value for key, value in item.items() if key != "file_data"} for item in client_documents_db.values() if item["client_id"] == client_id]

@router.get("/api/v1/clients/{client_id}/medical-documents/{document_id}", dependencies=[Depends(require_client_record_access)], tags=["2. Patient Health & History"])
def download_medical_document(client_id: str, document_id: str):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT content_type, file_data FROM client_medical_document WHERE client_id = %s AND document_id = %s", (client_id, document_id))
            document = cursor.fetchone()
    else:
        document = client_documents_db.get(document_id)
        if document and document["client_id"] != client_id:
            document = None
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(content=bytes(document["file_data"]), media_type=document["content_type"], headers={"Content-Disposition": "inline"})
