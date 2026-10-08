"""Small helpers shared by several API areas."""
import json
from fastapi import HTTPException
import database
import config
from state import users_db


def email_is_registered(email: str) -> bool:
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM dietitian WHERE LOWER(email) = LOWER(%s) "
                "UNION ALL SELECT 1 FROM client WHERE LOWER(email) = LOWER(%s) LIMIT 1",
                (email, email),
            )
            return cursor.fetchone() is not None
    return any(user["email"].casefold() == email.casefold() for user in users_db.values())


def fetch_client_profile(cursor, client_id: str) -> dict:
    cursor.execute("SELECT client_id FROM client WHERE client_id = %s", (client_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Patient record not found")
    cursor.execute(
        "SELECT a.name AS allergen, ca.severity FROM client_allergy ca "
        "JOIN allergen a ON a.allergen_id = ca.allergen_id WHERE ca.client_id = %s ORDER BY a.name",
        (client_id,),
    )
    allergies = [{**dict(row), "severity": row["severity"].lower()} for row in cursor.fetchall()]
    cursor.execute(
        "SELECT mc.name AS condition_name, mc.icd_code, cmc.severity "
        "FROM client_medical_condition cmc JOIN medical_condition mc ON mc.condition_id = cmc.condition_id "
        "WHERE cmc.client_id = %s ORDER BY mc.name",
        (client_id,),
    )
    conditions = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        "SELECT mt.name AS metric_type, cml.value FROM client_metric_log cml "
        "JOIN metric_type mt ON mt.metric_type_id = cml.metric_type_id "
        "WHERE cml.client_id = %s ORDER BY cml.recorded_at",
        (client_id,),
    )
    metrics = [{"metric_type": row["metric_type"], "value": str(row["value"])} for row in cursor.fetchall()]
    cursor.execute(
        "SELECT weight AS weight_kg, calories_consumed AS calories, steps, "
        "sleep_minutes / 60.0 AS sleep_hours FROM progress_log "
        "WHERE client_id = %s ORDER BY log_date",
        (client_id,),
    )
    progress = [dict(row) for row in cursor.fetchall()]
    profile = {"allergies": allergies, "conditions": conditions, "metrics": metrics, "progress": progress}
    cursor.execute(
        "SELECT due_date, notes FROM pregnancy_profile WHERE client_id = %s AND is_active "
        "ORDER BY pregnancy_id DESC LIMIT 1",
        (client_id,),
    )
    pregnancy = cursor.fetchone()
    if pregnancy:
        pregnancy_data = json.loads(pregnancy["notes"] or "{}")
        pregnancy_data["due_date"] = pregnancy["due_date"].isoformat()
        profile["pregnancy"] = pregnancy_data
    cursor.execute(
        "SELECT notes FROM lactation_profile WHERE client_id = %s AND end_date IS NULL "
        "ORDER BY start_date DESC LIMIT 1",
        (client_id,),
    )
    lactation = cursor.fetchone()
    if lactation:
        profile["lactation"] = {"is_active": True, "notes": lactation["notes"]}
    return profile


def decode_recommendation(row: dict) -> dict:
    stored_text = row["recommendation_text"]
    try:
        details = json.loads(stored_text)
    except (TypeError, json.JSONDecodeError):
        details = {"dietary_goal": "", "generated_plan": [stored_text]}
    return {
        "recommendation_id": row["recommendation_id"],
        "client_id": row["client_id"],
        "dietary_goal": details.get("dietary_goal", ""),
        "generated_plan": details.get("generated_plan", []),
        "status": row["status"],
        **({"review_notes": row["client_feedback"]} if row.get("client_feedback") else {}),
    }


def build_full_name(first_name, last_name):
    return f"{first_name.strip()} {last_name.strip()}".strip()
