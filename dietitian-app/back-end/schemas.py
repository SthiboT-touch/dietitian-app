"""Pydantic request/response models shared by all API areas."""
from fastapi import status
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import date


class DietitianRegister(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: str
    license_number: str
    password: str = Field(..., min_length=8)

class ClientRegister(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: str
    dietitian_id: Optional[str] = None
    date_of_birth: date
    password: str = Field(..., min_length=8)

class LoginRequest(BaseModel):
    email: str
    password: str


class AdminSetup(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: str
    password: str = Field(..., min_length=8)


class AdminApproval(BaseModel):
    dietitian_id: str
    status: Literal["APPROVED", "REJECTED"]
    notes: Optional[str] = None

class BranchCreate(BaseModel):
    name: str
    address: str
    business_id: Optional[str] = None

# Section 2 Schemas
class PregnancyLog(BaseModel):
    trimester: int = Field(..., ge=1, le=3)
    due_date: str

class LactationLog(BaseModel):
    is_active: bool
    notes: Optional[str] = None

class AllergyEntry(BaseModel):
    allergen: str
    severity: Literal["mild", "moderate", "severe", "anaphylactic"]

class MedicalConditionEntry(BaseModel):
    condition_name: str
    icd_code: Optional[str] = None

# Section 3 Schemas
class MetricLog(BaseModel):
    metric_type: str
    value: str

class ProgressLog(BaseModel):
    weight_kg: Optional[float] = None
    body_fat_pct: Optional[float] = None
    waist_cm: Optional[float] = None
    calories: Optional[int] = None
    water_ml: Optional[int] = None
    steps: Optional[int] = None
    sleep_hours: Optional[float] = None

# Section 4 Schemas
class AppointmentCreate(BaseModel):
    client_id: str
    dietitian_id: str
    appointment_date: str

class AppointmentDecision(BaseModel):
    action: Literal["APPROVED", "REJECTED", "CANCELLED"]

class GoalCreate(BaseModel):
    client_id: str
    target_metric: str
    target_value: float

# Section 5 Schemas
class FoodItem(BaseModel):
    food_id: str
    name: str
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    glycemic_index: Optional[int] = None

class RecipeCreate(BaseModel):
    title: str
    ingredients: List[str]
    instructions: str

class MealPlanRequest(BaseModel):
    client_id: str
    diet_type: str
    days: int = Field(default=7, ge=1, le=30)

class MealPlanResponse(BaseModel):
    meal_plan_id: str
    client_id: str
    diet_type: str
    days: int
    meals: List[str]
    status: str = "GENERATED"

class AIGenerateRequest(BaseModel):
    client_id: str
    dietary_goal: str

class AIChatRequest(BaseModel):
    user_id: str
    role: Literal["client", "dietitian"]
    message: str = Field(..., min_length=1)

class RecommendationReview(BaseModel):
    action: Literal["APPROVED", "MODIFIED", "REJECTED"]
    notes: Optional[str] = None
