"""5. Foods, recipes and meal plans."""
import json
import uuid
from fastapi import APIRouter, HTTPException, status
from typing import List, Optional
import database
import config
from state import users_db, meal_plans_db, recipes_db, foods_db
from schemas import FoodItem, RecipeCreate, MealPlanRequest, MealPlanResponse


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
def create_meal_plan(request: MealPlanRequest):
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

@router.get("/api/v1/meal-plans", response_model=List[MealPlanResponse], tags=["5. Foods & Meal Planning"])
def list_meal_plans(dietitian_id: Optional[str] = None, client_id: Optional[str] = None):
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
                plans.append({
                    **dict(plan),
                    "meals": json.loads(day["notes"]) if day and day["notes"] else [],
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
def get_meal_plan(meal_plan_id: str):
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
            cursor.execute(
                "SELECT notes FROM meal_plan_day WHERE meal_plan_id = %s ORDER BY day_number LIMIT 1",
                (meal_plan_id,),
            )
            day = cursor.fetchone()
        return {
            **dict(plan),
            "meals": json.loads(day["notes"]) if day and day["notes"] else [],
            "status": "GENERATED",
        }
    if meal_plan_id not in meal_plans_db:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    return meal_plans_db[meal_plan_id]
