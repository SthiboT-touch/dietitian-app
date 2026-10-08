"""2. Patient health history and 3. clinical labs and daily progress."""
import json
from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import date
import database
import config
from state import users_db, clients_db
from schemas import PregnancyLog, LactationLog, AllergyEntry, MedicalConditionEntry, MetricLog, ProgressLog
from helpers import fetch_client_profile


router = APIRouter()


# --- 2. PATIENT HEALTH, LIFE STAGE & CLINICAL HISTORY ---

@router.get("/api/v1/clients", tags=["2. Patient Health & History"])
def list_clients(dietitian_id: Optional[str] = None, client_id: Optional[str] = None):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            if client_id:
                cursor.execute(
                    "SELECT client_id AS id, name, dietitian_id, status FROM client WHERE client_id = %s",
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
        }
        for user in sorted(clients, key=lambda item: item["full_name"].casefold())
    ]


@router.get("/api/v1/clients/{client_id}/profile", tags=["2. Patient Health & History"])
def get_client_profile(client_id: str):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            return fetch_client_profile(cursor, client_id)
    if client_id not in clients_db:
        clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    return clients_db[client_id]

@router.post("/api/v1/clients/{client_id}/pregnancy", tags=["2. Patient Health & History"])
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

@router.post("/api/v1/clients/{client_id}/lactation", tags=["2. Patient Health & History"])
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

@router.post("/api/v1/clients/{client_id}/allergies", tags=["2. Patient Health & History"])
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

@router.post("/api/v1/clients/{client_id}/medical-conditions", tags=["2. Patient Health & History"])
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

@router.post("/api/v1/clients/{client_id}/metrics", tags=["3. Clinical Labs & Progress"])
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

@router.get("/api/v1/clients/{client_id}/metrics", tags=["3. Clinical Labs & Progress"])
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

@router.post("/api/v1/clients/{client_id}/progress", tags=["3. Clinical Labs & Progress"])
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

@router.get("/api/v1/clients/{client_id}/progress", tags=["3. Clinical Labs & Progress"])
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
