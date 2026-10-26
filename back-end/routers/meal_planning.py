"""5. Foods, recipes and meal plans."""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
import database
import config
from state import users_db, meal_plans_db, recipes_db, foods_db
from schemas import FoodItem, FoodItemCreate, RecipeCreate, MealPlanRequest, MealPlanResponse
from security import require_admin, require_dietitian, require_client
from clinical_screening import screen_meal_plan_context
from pydantic import BaseModel, Field


router = APIRouter()


class MealPlanScreeningRequest(BaseModel):
    client_id: str
    diet_type: str
    days: int = Field(default=7, ge=1, le=30)
    allergies: Optional[List[str]] = None
    conditions: Optional[List[str]] = None
    life_stage: Optional[str] = None
    ingredients: Optional[List[str]] = None


def _verify_client_assignment(client_id: str, dietitian_id: str) -> None:
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT dietitian_id FROM client WHERE client_id = %s", (client_id,))
            client = cursor.fetchone()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        assigned = client["dietitian_id"]
    else:
        client = next((u for u in users_db.values() if str(u.get("id")) == str(client_id) and u.get("type") == "client"), None)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        assigned = client.get("dietitian_id")
    if str(assigned) != str(dietitian_id):
        raise HTTPException(status_code=403, detail="Client is not assigned to this dietitian")


@router.post("/api/v1/meal-plans/screen", tags=["5. Foods & Meal Planning"])
def screen_meal_plan(data: MealPlanScreeningRequest, dietitian_id: str = Depends(require_dietitian)):
    """Authenticated preflight only; never certifies a meal as clinically safe."""
    _verify_client_assignment(data.client_id, dietitian_id)
    result = screen_meal_plan_context(**data.model_dump())
    return {"ready_for_review": result.ready_for_review,
            "blockers": result.blockers, "cautions": result.cautions,
            "clinical_approval": False}



class MealDraftRequest(MealPlanScreeningRequest):
    """Dietitian-reviewed context. Empty lists mean explicitly reviewed none."""
    recipe_ids: List[str] = Field(default_factory=list, min_length=1, max_length=30)


def _load_candidate_recipes(recipe_ids: List[str]) -> list[dict]:
    if len(set(recipe_ids)) != len(recipe_ids):
        raise HTTPException(status_code=422, detail="Duplicate recipe IDs are not allowed")
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT recipe_id, name, instructions FROM recipe WHERE recipe_id = ANY(%s)",
                (recipe_ids,),
            )
            rows = cursor.fetchall()
        recipes = []
        for row in rows:
            try:
                data = json.loads(row["instructions"])
            except (TypeError, ValueError):
                data = {}
            recipes.append({"recipe_id": row["recipe_id"], "title": row["name"],
                            "ingredients": data.get("ingredients", []),
                            "instructions": data.get("instructions", "")})
    else:
        recipes = [recipes_db[key] for key in recipe_ids if key in recipes_db]
    indexed = {str(r["recipe_id"]): r for r in recipes}
    if any(key not in indexed for key in recipe_ids):
        raise HTTPException(status_code=422, detail="Every selected recipe must exist")
    return [indexed[key] for key in recipe_ids]


@router.post("/api/v1/meal-plans/draft", tags=["5. Foods & Meal Planning"])
def preview_meal_plan_draft(data: MealDraftRequest, dietitian_id: str = Depends(require_dietitian)):
    """Non-persisted draft preview, never a clinical prescription or client publication."""
    _verify_client_assignment(data.client_id, dietitian_id)
    recipes = _load_candidate_recipes(data.recipe_ids)
    ingredients = []
    for recipe in recipes:
        if not recipe.get("ingredients") or not isinstance(recipe["ingredients"], list):
            raise HTTPException(status_code=422, detail="Recipes must have ingredient lists")
        ingredients.extend(str(x) for x in recipe["ingredients"])
    result = screen_meal_plan_context(
        client_id=data.client_id, diet_type=data.diet_type, days=data.days,
        allergies=data.allergies, conditions=data.conditions,
        life_stage=data.life_stage, ingredients=ingredients,
    )
    if not result.ready_for_review:
        raise HTTPException(status_code=422, detail={"blockers": result.blockers,
                                                     "cautions": result.cautions})
    schedule = [
        {"day": day, "candidate_recipe": {
            "recipe_id": recipes[(day - 1) % len(recipes)]["recipe_id"],
            "title": recipes[(day - 1) % len(recipes)]["title"]}}
        for day in range(1, data.days + 1)
    ]
    return {"status": "DRAFT_PREVIEW", "published": False, "saved": False,
            "clinical_approval": False, "client_id": data.client_id,
            "diet_type": data.diet_type, "life_stage": data.life_stage,
            "days": data.days, "schedule": schedule,
            "cautions": result.cautions + [
                "Recipe rotation is not a nutritional prescription; portions, adequacy, "
                "ingredient derivatives, and condition-specific restrictions need dietitian review."],
            "message": "Preview only. No plan has been saved or shared with the client."}




# Phase 3: separate approval workflow; existing meal_plan tables remain unchanged.
# Development-only memory store is intentionally not durable. PostgreSQL is required
# for persistent drafts and approvals.
from datetime import datetime, timezone
from threading import RLock
from copy import deepcopy

_draft_store = {}
_draft_lock = RLock()

class DraftSaveRequest(MealDraftRequest):
    pass

class DraftDecisionRequest(BaseModel):
    decision: str
    revised_schedule: Optional[List[dict]] = None
    review_note: str = Field(min_length=1, max_length=2000)


def _fetch_draft(plan_id: str) -> dict:
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT plan_id, client_id, dietitian_id, status, draft_json, approved_json, review_note, reviewed_at FROM meal_plan_review WHERE plan_id=%s", (plan_id,))
            record = cursor.fetchone()
            if record:
                return dict(record)
    else:
        with _draft_lock:
            record = deepcopy(_draft_store.get(plan_id))
            if record:
                return record
    raise HTTPException(status_code=404, detail="Meal plan draft not found")


def _owner(record: dict, dietitian_id: str):
    if str(record["dietitian_id"]) != str(dietitian_id):
        raise HTTPException(status_code=403, detail="Not your assigned meal plan")
    _verify_client_assignment(str(record["client_id"]), dietitian_id)


@router.post("/api/v1/meal-plans/drafts", status_code=201, tags=["5. Foods & Meal Planning"])
def save_meal_draft(data: DraftSaveRequest, dietitian_id: str = Depends(require_dietitian)):
    preview = preview_meal_plan_draft(data, dietitian_id)
    plan_id = str(uuid.uuid4())
    draft = {"client_id": data.client_id, "diet_type": data.diet_type,
             "life_stage": data.life_stage, "days": data.days,
             "allergies": data.allergies, "conditions": data.conditions,
             "recipe_ids": data.recipe_ids, "schedule": preview["schedule"],
             "cautions": preview["cautions"]}
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("INSERT INTO meal_plan_review (plan_id,client_id,dietitian_id,status,draft_json) VALUES (%s,%s,%s,'PENDING_REVIEW',%s::jsonb)",
                           (plan_id, data.client_id, dietitian_id, json.dumps(draft)))
    else:
        with _draft_lock:
            _draft_store[plan_id] = {"plan_id": plan_id, "client_id": data.client_id,
                                      "dietitian_id": dietitian_id, "status": "PENDING_REVIEW",
                                      "draft_json": draft, "approved_json": None,
                                      "review_note": None, "reviewed_at": None}
    return {"plan_id": plan_id, "status": "PENDING_REVIEW", "published": False}


@router.get("/api/v1/meal-plans/review-queue", tags=["5. Foods & Meal Planning"])
def list_review_queue(dietitian_id: str = Depends(require_dietitian)):
    """Return only drafts assigned to the signed-in dietitian."""
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT plan_id, client_id, dietitian_id, status, draft_json, approved_json, review_note, reviewed_at FROM meal_plan_review WHERE dietitian_id=%s ORDER BY created_at DESC", (dietitian_id,))
            records = [dict(row) for row in cursor.fetchall()]
    else:
        with _draft_lock:
            records = [deepcopy(row) for row in _draft_store.values() if str(row["dietitian_id"]) == str(dietitian_id)]
    return records


@router.get("/api/v1/meal-plans/drafts/{plan_id}", tags=["5. Foods & Meal Planning"])
def get_meal_draft(plan_id: str, dietitian_id: str = Depends(require_dietitian)):
    record = _fetch_draft(plan_id)
    _owner(record, dietitian_id)
    return record


@router.post("/api/v1/meal-plans/drafts/{plan_id}/decision", tags=["5. Foods & Meal Planning"])
def review_meal_draft(plan_id: str, data: DraftDecisionRequest, dietitian_id: str = Depends(require_dietitian)):
    decision = data.decision.upper().strip()
    if decision not in {"APPROVED", "MODIFIED", "REJECTED"}:
        raise HTTPException(status_code=422, detail="Invalid review decision")
    if decision == "MODIFIED" and not data.revised_schedule:
        raise HTTPException(status_code=422, detail="Modified plans require a revised schedule")
    if decision != "MODIFIED" and data.revised_schedule is not None:
        raise HTTPException(status_code=422, detail="Revised schedule is only valid for MODIFIED")
    record = _fetch_draft(plan_id)
    _owner(record, dietitian_id)
    approved = None
    if decision != "REJECTED":
        approved = deepcopy(record["draft_json"])
        if decision == "MODIFIED":
            schedule = data.revised_schedule
            expected_days = approved["days"]
            if len(schedule) != expected_days or sorted(x.get("day") for x in schedule if isinstance(x, dict)) != list(range(1, expected_days+1)):
                raise HTTPException(status_code=422, detail="Revised schedule must cover each day exactly once")
            # Reviewed free-text schedule; dietitian remains responsible for safety.
            approved["schedule"] = schedule
    now = datetime.now(timezone.utc).isoformat()
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("UPDATE meal_plan_review SET status=%s, approved_json=%s::jsonb, review_note=%s, reviewed_at=NOW() WHERE plan_id=%s AND dietitian_id=%s AND status='PENDING_REVIEW' RETURNING plan_id",
                           (decision, json.dumps(approved) if approved else None, data.review_note, plan_id, dietitian_id))
            if not cursor.fetchone():
                raise HTTPException(status_code=409, detail="Draft has already been reviewed")
    else:
        with _draft_lock:
            current = _draft_store.get(plan_id)
            if not current or current["status"] != "PENDING_REVIEW":
                raise HTTPException(status_code=409, detail="Draft has already been reviewed")
            current.update(status=decision, approved_json=approved, review_note=data.review_note, reviewed_at=now)
    return {"plan_id": plan_id, "status": decision, "published": decision in {"APPROVED", "MODIFIED"}}


@router.get("/api/v1/meal-plans/approved", tags=["5. Foods & Meal Planning"])
def list_client_approved_meal_plans(client_id: str = Depends(require_client)):
    """Only published plans for the authenticated client; no client ID query parameter."""
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                    "SELECT plan_id, status, approved_json, reviewed_at FROM meal_plan_review "
                    "WHERE client_id=%s AND status IN ('APPROVED','MODIFIED') "
                    "AND approved_json IS NOT NULL ORDER BY reviewed_at DESC",
                    (client_id,),
                )
            rows = cursor.fetchall()
    else:
        with _draft_lock:
            rows = [deepcopy(record) for record in _draft_store.values()
                if str(record['client_id']) == str(client_id)
                and record['status'] in {'APPROVED', 'MODIFIED'}
                and record.get('approved_json')]
    return [{'plan_id': str(row['plan_id']), 'status': row['status'],
             'plan': row['approved_json']} for row in rows]


@router.get("/api/v1/meal-plans/approved/{plan_id}", tags=["5. Foods & Meal Planning"])
def client_approved_meal_plan(plan_id: str, client_id: str = Depends(require_client)):
    record = _fetch_draft(plan_id)
    if str(record["client_id"]) != str(client_id):
        raise HTTPException(status_code=404, detail="Meal plan not found")
    if record["status"] not in {"APPROVED", "MODIFIED"} or not record["approved_json"]:
        raise HTTPException(status_code=404, detail="Approved meal plan not found")
    return {"plan_id": plan_id, "status": record["status"], "plan": record["approved_json"]}


# --- 5. FOODS, RECIPES & MEAL PLANNING ---

@router.get("/api/v1/foods", response_model=List[FoodItem], tags=["5. Foods & Meal Planning"])
def get_foods():
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT food_item_id AS food_id, name, calories, protein AS protein_g, "
                "carbs AS carbs_g, fat AS fat_g, glycemic_index FROM food_item ORDER BY name"
            )
            return [
                {
                    **dict(row),
                    "calories": round(row["calories"]),
                    "protein_g": float(row["protein_g"] or 0),
                    "carbs_g": float(row["carbs_g"] or 0),
                    "fat_g": float(row["fat_g"] or 0),
                }
                for row in cursor.fetchall()
            ]
    return foods_db


@router.post(
    "/api/v1/foods",
    response_model=FoodItem,
    status_code=status.HTTP_201_CREATED,
    tags=["5. Foods & Meal Planning"],
)
def create_food(data: FoodItemCreate, admin_id: str = Depends(require_admin)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Food name is required")
    food_id = str(uuid.uuid4())
    food = {
        "food_id": food_id,
        "name": name,
        "calories": data.calories,
        "protein_g": data.protein_g,
        "carbs_g": data.carbs_g,
        "fat_g": data.fat_g,
        "glycemic_index": data.glycemic_index,
    }
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM food_item WHERE LOWER(name) = LOWER(%s) LIMIT 1",
                (name,),
            )
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="A food with this name already exists")
            cursor.execute(
                "INSERT INTO food_item "
                "(food_item_id, name, calories, protein, carbs, fat, glycemic_index) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    food_id,
                    name,
                    data.calories,
                    data.protein_g,
                    data.carbs_g,
                    data.fat_g,
                    data.glycemic_index,
                ),
            )
    else:
        if any(existing["name"].casefold() == name.casefold() for existing in foods_db):
            raise HTTPException(status_code=409, detail="A food with this name already exists")
        foods_db.append(food)
    return food


@router.post("/api/v1/recipes", tags=["5. Foods & Meal Planning"])
def create_recipe(data: RecipeCreate):
    recipe_id = f"rec_{uuid.uuid4().hex[:8]}"
    if config.DATABASE_ENABLED:
        stored_instructions = json.dumps({
            "instructions": data.instructions,
            "ingredients": data.ingredients,
        })
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO recipe (recipe_id, name, instructions) VALUES (%s, %s, %s)",
                (recipe_id, data.title, stored_instructions),
            )
    else:
        recipes_db[recipe_id] = {"recipe_id": recipe_id, **data.model_dump()}
    return {"message": "Recipe created", "recipe_id": recipe_id, "details": data.model_dump()}


@router.get("/api/v1/recipes", tags=["5. Foods & Meal Planning"])
def list_recipes():
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT recipe_id, name, instructions FROM recipe ORDER BY LOWER(name)")
            recipes = []
            for row in cursor.fetchall():
                try:
                    stored = json.loads(row["instructions"])
                except (TypeError, json.JSONDecodeError):
                    stored = {"instructions": row["instructions"], "ingredients": []}
                recipes.append({
                    "recipe_id": row["recipe_id"],
                    "title": row["name"],
                    "ingredients": stored.get("ingredients", []),
                    "instructions": stored.get("instructions", ""),
                })
            return recipes
    return sorted(
        [
            {"recipe_id": recipe["recipe_id"], "title": recipe["title"],
             "ingredients": recipe["ingredients"], "instructions": recipe["instructions"]}
            for recipe in recipes_db.values()
        ],
        key=lambda recipe: recipe["title"].casefold(),
    )

@router.post("/api/v1/meal-plans", response_model=MealPlanResponse, status_code=status.HTTP_201_CREATED, tags=["5. Foods & Meal Planning"])
def create_meal_plan(request: MealPlanRequest, dietitian_id: str = Depends(require_dietitian)):
    _verify_client_assignment(request.client_id, dietitian_id)
    raise HTTPException(
        status_code=409,
        detail="Sample-meal generation is disabled pending reviewed recipes, clinical context and dietitian approval. Use /api/v1/meal-plans/screen for preflight checks.",
    )
    plan_id = f"plan_{uuid.uuid4().hex[:8]}"
    sample_meals = [
        f"Breakfast: Oatmeal with chia seeds ({request.diet_type})",
        "Lunch: Quinoa bowl with grilled chicken",
        "Dinner: Salmon with steamed broccoli"
    ]
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT dietitian_id FROM client WHERE client_id = %s", (request.client_id,))
            client = cursor.fetchone()
            if not client:
                raise HTTPException(status_code=404, detail="Patient record not found")
            if not client["dietitian_id"]:
                raise HTTPException(status_code=422, detail="Patient must be linked to a dietitian")
            cursor.execute(
                "INSERT INTO diet_type (name) VALUES (%s) ON CONFLICT (name) DO UPDATE "
                "SET name = EXCLUDED.name RETURNING diet_type_id",
                (request.diet_type,),
            )
            diet_type_id = cursor.fetchone()["diet_type_id"]
            cursor.execute(
                "INSERT INTO meal_plan (meal_plan_id, client_id, dietitian_id, diet_type_id, start_date, end_date) "
                "VALUES (%s, %s, %s, %s, CURRENT_DATE, CURRENT_DATE + %s - 1)",
                (plan_id, request.client_id, client["dietitian_id"], diet_type_id, request.days),
            )
            for day_number in range(1, request.days + 1):
                cursor.execute(
                    "INSERT INTO meal_plan_day (meal_plan_id, day_number, notes) VALUES (%s, %s, %s)",
                    (plan_id, day_number, json.dumps(sample_meals)),
                )
        return {
            "meal_plan_id": plan_id,
            "client_id": request.client_id,
            "diet_type": request.diet_type,
            "days": request.days,
            "meals": sample_meals,
            "status": "GENERATED",
        }
    plan_data = {
        "meal_plan_id": plan_id,
        "client_id": request.client_id,
        "diet_type": request.diet_type,
        "days": request.days,
        "meals": sample_meals,
        "status": "GENERATED"
    }
    meal_plans_db[plan_id] = plan_data
    return plan_data

# Legacy meal-plan endpoints are retained for compatibility with dietitian screens,
# but cannot be used as an unauthenticated client data lookup.
@router.get("/api/v1/meal-plans", response_model=List[MealPlanResponse], tags=["5. Foods & Meal Planning"])
def list_meal_plans(dietitian_id: str = Depends(require_dietitian)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT mp.meal_plan_id, mp.client_id, COALESCE(dt.name, 'Standard') AS diet_type, "
                "COALESCE(mp.end_date - mp.start_date + 1, 1) AS days "
                "FROM meal_plan mp LEFT JOIN diet_type dt ON dt.diet_type_id = mp.diet_type_id "
                "WHERE mp.dietitian_id=%s ORDER BY mp.start_date DESC", (dietitian_id,))
            plans = []
            for plan in cursor.fetchall():
                cursor.execute("SELECT notes FROM meal_plan_day WHERE meal_plan_id=%s ORDER BY day_number LIMIT 1", (plan["meal_plan_id"],))
                day = cursor.fetchone()
                plans.append({**dict(plan), "meals": json.loads(day["notes"]) if day and day["notes"] else [], "status": "GENERATED"})
            return plans
    assigned = {str(user["id"]) for user in users_db.values()
                if user.get("type") == "client" and str(user.get("dietitian_id")) == str(dietitian_id)}
    return sorted([plan for plan in meal_plans_db.values() if str(plan["client_id"]) in assigned],
                  key=lambda plan: plan["meal_plan_id"], reverse=True)


@router.get("/api/v1/meal-plans/{meal_plan_id}", response_model=MealPlanResponse, tags=["5. Foods & Meal Planning"])
def get_meal_plan(meal_plan_id: str, dietitian_id: str = Depends(require_dietitian)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT mp.meal_plan_id, mp.client_id, dt.name AS diet_type, "
                "(mp.end_date - mp.start_date + 1) AS days "
                "FROM meal_plan mp LEFT JOIN diet_type dt ON dt.diet_type_id=mp.diet_type_id "
                "WHERE mp.meal_plan_id=%s AND mp.dietitian_id=%s", (meal_plan_id, dietitian_id))
            plan = cursor.fetchone()
            if not plan:
                raise HTTPException(status_code=404, detail="Meal plan not found")
            cursor.execute("SELECT notes FROM meal_plan_day WHERE meal_plan_id=%s ORDER BY day_number LIMIT 1", (meal_plan_id,))
            day = cursor.fetchone()
        return {**dict(plan), "meals": json.loads(day["notes"]) if day and day["notes"] else [], "status": "GENERATED"}
    plan = meal_plans_db.get(meal_plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    _verify_client_assignment(str(plan["client_id"]), dietitian_id)
    return plan
