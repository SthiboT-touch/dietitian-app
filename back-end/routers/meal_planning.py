"""5. Foods, recipes and meal plans."""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
import database
import config
from state import users_db, meal_plans_db, recipes_db, foods_db, clients_db
from schemas import FoodItem, FoodItemCreate, RecipeCreate, MealPlanRequest, MealPlanResponse
from security import Principal, require_admin, require_session
from access import require_client_access, require_staff
from helpers import fetch_client_profile
from routers.ai import generate_llama_meal_plan


router = APIRouter()


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
def create_recipe(data: RecipeCreate, principal: Principal = Depends(require_session)):
    require_staff(principal)
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
def list_recipes(principal: Principal = Depends(require_session)):
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

def _decode_day_notes(notes) -> tuple:
    """A plan day stores a JSON list of meals, or {"meals": [...], "grocery_list": [...]} for AI plans."""
    if not notes:
        return [], []
    stored = json.loads(notes)
    if isinstance(stored, dict):
        return list(stored.get("meals", [])), list(stored.get("grocery_list", []))
    return list(stored), []


def _store_meal_plan(request: MealPlanRequest, meals: List[str], grocery_list: List[str]) -> dict:
    plan_id = f"plan_{uuid.uuid4().hex[:8]}"
    plan_data = {
        "meal_plan_id": plan_id,
        "client_id": request.client_id,
        "diet_type": request.diet_type,
        "days": request.days,
        "meals": meals,
        "grocery_list": grocery_list,
        "status": "GENERATED",
    }
    if config.DATABASE_ENABLED:
        day_notes = json.dumps({"meals": meals, "grocery_list": grocery_list} if grocery_list else meals)
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
                    (plan_id, day_number, day_notes),
                )
        return plan_data
    meal_plans_db[plan_id] = plan_data
    return plan_data


@router.post("/api/v1/meal-plans", response_model=MealPlanResponse, status_code=status.HTTP_201_CREATED, tags=["5. Foods & Meal Planning"])
def create_meal_plan(request: MealPlanRequest, principal: Principal = Depends(require_session)):
    require_staff(principal)
    require_client_access(principal, request.client_id)
    sample_meals = [
        f"Breakfast: Oatmeal with chia seeds ({request.diet_type})",
        "Lunch: Quinoa bowl with grilled chicken",
        "Dinner: Salmon with steamed broccoli"
    ]
    return _store_meal_plan(request, sample_meals, [])


@router.post("/api/v1/meal-plans/ai", response_model=MealPlanResponse, status_code=status.HTTP_201_CREATED, tags=["5. Foods & Meal Planning"])
def create_ai_meal_plan(request: MealPlanRequest, principal: Principal = Depends(require_session)):
    """Draft a plan with the AI model, using the patient's allergies and conditions, plus a grocery list."""
    require_staff(principal)
    require_client_access(principal, request.client_id)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            profile = fetch_client_profile(cursor, request.client_id)
    else:
        profile = clients_db.get(request.client_id, {})
    draft = generate_llama_meal_plan(request.diet_type, request.days, profile)
    return _store_meal_plan(request, draft["meals"], draft["grocery_list"])


@router.get("/api/v1/meal-plans", response_model=List[MealPlanResponse], tags=["5. Foods & Meal Planning"])
def list_meal_plans(
    dietitian_id: Optional[str] = None,
    client_id: Optional[str] = None,
    principal: Principal = Depends(require_session),
):
    if client_id:
        require_client_access(principal, client_id)
    elif dietitian_id and (
        principal.role == "client" or (principal.role == "dietitian" and principal.id != dietitian_id)
    ):
        raise HTTPException(status_code=403, detail="You can only list your own meal plans")
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            if client_id:
                cursor.execute(
                    "SELECT mp.meal_plan_id, mp.client_id, COALESCE(dt.name, 'Standard') AS diet_type, "
                    "COALESCE(mp.end_date - mp.start_date + 1, 1) AS days "
                    "FROM meal_plan mp LEFT JOIN diet_type dt ON dt.diet_type_id = mp.diet_type_id "
                    "WHERE mp.client_id = %s ORDER BY mp.start_date DESC",
                    (client_id,),
                )
            elif dietitian_id:
                cursor.execute(
                    "SELECT mp.meal_plan_id, mp.client_id, COALESCE(dt.name, 'Standard') AS diet_type, "
                    "COALESCE(mp.end_date - mp.start_date + 1, 1) AS days "
                    "FROM meal_plan mp LEFT JOIN diet_type dt ON dt.diet_type_id = mp.diet_type_id "
                    "WHERE mp.dietitian_id = %s ORDER BY mp.start_date DESC",
                    (dietitian_id,),
                )
            else:
                return []
            plans = []
            for plan in cursor.fetchall():
                cursor.execute(
                    "SELECT notes FROM meal_plan_day WHERE meal_plan_id = %s ORDER BY day_number LIMIT 1",
                    (plan["meal_plan_id"],),
                )
                day = cursor.fetchone()
                meals, grocery_list = _decode_day_notes(day["notes"] if day else None)
                plans.append({
                    **dict(plan),
                    "meals": meals,
                    "grocery_list": grocery_list,
                    "status": "GENERATED",
                })
            return plans
    if client_id:
        plans = [plan for plan in meal_plans_db.values() if plan["client_id"] == client_id]
    elif dietitian_id:
        client_ids = {
            user["id"] for user in users_db.values()
            if user.get("type") == "client" and user.get("dietitian_id") == dietitian_id
        }
        plans = [plan for plan in meal_plans_db.values() if plan["client_id"] in client_ids]
    else:
        plans = []
    return sorted(plans, key=lambda plan: plan["meal_plan_id"], reverse=True)


@router.get("/api/v1/meal-plans/{meal_plan_id}", response_model=MealPlanResponse, tags=["5. Foods & Meal Planning"])
def get_meal_plan(meal_plan_id: str, principal: Principal = Depends(require_session)):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT mp.meal_plan_id, mp.client_id, dt.name AS diet_type, "
                "(mp.end_date - mp.start_date + 1) AS days "
                "FROM meal_plan mp LEFT JOIN diet_type dt ON dt.diet_type_id = mp.diet_type_id "
                "WHERE mp.meal_plan_id = %s",
                (meal_plan_id,),
            )
            plan = cursor.fetchone()
            if not plan:
                raise HTTPException(status_code=404, detail="Meal plan not found")
            require_client_access(principal, plan["client_id"])
            cursor.execute(
                "SELECT notes FROM meal_plan_day WHERE meal_plan_id = %s ORDER BY day_number LIMIT 1",
                (meal_plan_id,),
            )
            day = cursor.fetchone()
        meals, grocery_list = _decode_day_notes(day["notes"] if day else None)
        return {
            **dict(plan),
            "meals": meals,
            "grocery_list": grocery_list,
            "status": "GENERATED",
        }
    if meal_plan_id not in meal_plans_db:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    require_client_access(principal, meal_plans_db[meal_plan_id]["client_id"])
    return meal_plans_db[meal_plan_id]
