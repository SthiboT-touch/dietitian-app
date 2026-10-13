"""7. Calculators and other helper tools."""
from fastapi import APIRouter, Depends

from schemas import NutritionTargetsRequest
from security import Principal, require_session


router = APIRouter()

ACTIVITY_FACTORS = {
    "sedentary": 1.2,      # desk job, little exercise
    "light": 1.375,        # light exercise 1-3 days a week
    "moderate": 1.55,      # moderate exercise 3-5 days a week
    "active": 1.725,       # hard exercise 6-7 days a week
    "very_active": 1.9,    # very hard exercise or a physical job
}
GOAL_FACTORS = {"lose": 0.85, "maintain": 1.0, "gain": 1.10}
CALORIE_FLOOR = {"female": 1200, "male": 1500}  # never suggest less than this without clinical supervision


def calculate_nutrition_targets(data: NutritionTargetsRequest) -> dict:
    """Mifflin-St Jeor resting energy, scaled by activity and goal, with simple macro and water targets."""
    sex_constant = 5 if data.sex == "male" else -161
    bmr = 10 * data.weight_kg + 6.25 * data.height_cm - 5 * data.age + sex_constant
    maintenance = bmr * ACTIVITY_FACTORS[data.activity]
    target = maintenance * GOAL_FACTORS[data.goal]
    floor = CALORIE_FLOOR[data.sex]
    floor_applied = target < floor
    calories = round(max(target, floor))

    protein_g = round(1.6 * data.weight_kg)
    fat_g = round(calories * 0.25 / 9)
    carbs_g = max(round((calories - protein_g * 4 - fat_g * 9) / 4), 0)

    notes = [
        "These are general estimates for healthy adults, not medical advice. "
        "Your dietitian can adjust them for your health history.",
    ]
    if floor_applied:
        notes.append(
            f"The calculated target was below {floor} kcal, so it was raised to a safe minimum. "
            "Eating less than this should only be done under a dietitian's supervision."
        )
    notes.append("Targets differ during pregnancy and breastfeeding. Ask your dietitian before using them.")
    return {
        "bmr_kcal": round(bmr),
        "maintenance_kcal": round(maintenance),
        "target_calories_kcal": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "water_ml": int(round(data.weight_kg * 35, -1)),
        "calorie_floor_applied": floor_applied,
        "notes": notes,
    }


@router.post("/api/v1/tools/nutrition-targets", tags=["7. Tools"])
def nutrition_targets(data: NutritionTargetsRequest, principal: Principal = Depends(require_session)):
    return calculate_nutrition_targets(data)
