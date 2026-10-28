"""Food catalogue and recipe endpoints.

The URLs and JSON payloads are unchanged for backwards compatibility with
existing NutriCare screens. Recipe changes require an authenticated dietitian;
food creation remains restricted to system administrators.
"""
import json
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

import config
import database
from schemas import FoodItem, FoodItemCreate, RecipeCreate
from security import require_admin, require_dietitian
from state import foods_db, recipes_db

router = APIRouter()


class RecipeItem(BaseModel):
    recipe_id: str
    title: str
    ingredients: List[str]
    instructions: str


class RecipeCreated(BaseModel):
    message: str
    recipe_id: str
    details: RecipeCreate


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


@router.post("/api/v1/recipes", response_model=RecipeCreated, tags=["5. Foods & Meal Planning"], summary="Create a recipe (dietitian only)")
def create_recipe(data: RecipeCreate, dietitian_id: str = Depends(require_dietitian)):
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


@router.get("/api/v1/recipes", response_model=List[RecipeItem], tags=["5. Foods & Meal Planning"], summary="List recipe catalogue")
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

