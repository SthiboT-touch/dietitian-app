"""Pydantic request/response models shared by all API areas."""

from pydantic import BaseModel, Field, field_validator, ValidationInfo
from typing import List, Literal, Optional
from datetime import date
from registration_validation import (
    validate_email,
    validate_sa_phone,
    validate_sa_id,
    validate_sa_id_number,
)


class DietitianRegister(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: str
    license_number: str
    password: str = Field(..., min_length=8)

    @field_validator("email")
    @classmethod
    def email_format(cls, value: str) -> str:
        return validate_email(value)


class RegistrationAttachment(BaseModel):
    filename: str = Field(..., min_length=1, max_length=120)
    content_type: Literal["image/jpeg", "image/png", "application/pdf"]
    data_base64: str = Field(..., min_length=4, max_length=4_200_000)


class ClientRegister(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: str
    dietitian_id: Optional[str] = None
    id_number: str = Field(..., min_length=1, max_length=30)
    phone: str = Field(..., min_length=1, max_length=35)
    date_of_birth: date
    gender: Literal["male", "female", "other"]
    phone_number: Optional[str] = Field(default=None, max_length=30)
    consent_accepted: bool = False
    privacy_notice_acknowledged: bool = False
    consent_location: Optional[str] = Field(default=None, max_length=150)
    consent_date: Optional[date] = None
    consent_signatory_name: Optional[str] = Field(default=None, max_length=150)
    consent_signature: Optional[str] = Field(default=None, max_length=150)
    password: str = Field(..., min_length=8)
    # A clear, versioned decision is required for new patient registrations.
    # Literal[True] prevents false, missing, or arbitrary consent values.
    profile_photo: Optional[RegistrationAttachment] = None
    initial_document: Optional[RegistrationAttachment] = None
    consent_to_care: Literal[True]
    privacy_notice_version: Literal["2026-10-28-v1"]

    @field_validator("email")
    @classmethod
    def email_format(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value: str) -> str:
        return validate_sa_phone(value)

    @field_validator("id_number")
    @classmethod
    def id_format(cls, value: str) -> str:
        return validate_sa_id_number(value)

    @field_validator("date_of_birth")
    @classmethod
    def identity_consistency(cls, value: date, info: ValidationInfo) -> date:
        # Field-level validation avoids echoing the entire registration body,
        # including password, when a date/identity mismatch is rejected.
        if info.data.get("id_number"):
            validate_sa_id(info.data["id_number"], value)
        return value


class ClientProfileUpdate(BaseModel):
    phone_number: Optional[str] = Field(default=None, max_length=30)
    date_of_birth: Optional[date] = None
    gender: Optional[Literal["male", "female", "other"]] = None
    height: Optional[float] = Field(default=None, ge=30, le=300)
    activity_level: Optional[str] = Field(default=None, max_length=30)
    dietary_preferences: Optional[str] = Field(default=None, max_length=2000)


class LoginRequest(BaseModel):
    email: str
    password: str


class EmailVerificationSend(BaseModel):
    email: str


class EmailVerificationCheck(BaseModel):
    email: str
    method_id: str = Field(..., min_length=1)
    code: str = Field(..., min_length=4, max_length=12)


class AdminSetup(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: str
    password: str = Field(..., min_length=8)


class AdminCreate(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: str
    password: str = Field(..., min_length=8)
    role: Literal[
        "admin", "reception_staff", "branch_manager", "compliance", "executive", "content_manager"
    ] = "admin"


class AdminApproval(BaseModel):
    dietitian_id: str
    status: Literal["APPROVED", "REJECTED"]
    notes: Optional[str] = None


class BranchCreate(BaseModel):
    name: str
    address: str
    business_id: Optional[str] = None


class DietitianBranchCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    address: str = Field(..., min_length=1, max_length=255)


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


class LactationStatusEntry(BaseModel):
    feeding_status: Literal["breastfeeding", "formula_feeding", "combo"]
    infant_age_months: Optional[int] = Field(default=None, ge=0, le=36)
    infant_age_weeks: Optional[int] = Field(default=None, ge=0, le=156)
    infant_birth_date: Optional[date] = None
    notes: Optional[str] = None


class DailyFeedingLog(BaseModel):
    feed_date: Optional[date] = None
    breastfeeding_sessions: int = Field(default=0, ge=0, le=30)
    pumping_sessions: int = Field(default=0, ge=0, le=20)
    expressed_milk_ml: float = Field(default=0, ge=0)
    formula_ml: float = Field(default=0, ge=0)
    formula_feeds: int = Field(default=0, ge=0, le=30)
    wet_diapers: Optional[int] = Field(default=None, ge=0, le=30)
    dirty_diapers: Optional[int] = Field(default=None, ge=0, le=30)
    notes: Optional[str] = None


class MilkSupplyLog(BaseModel):
    concern: Literal["low_supply", "over_supply"]
    log_date: Optional[date] = None
    pumped_ml_24h: Optional[float] = Field(default=None, ge=0)
    strategies_tried: Optional[str] = None
    notes: Optional[str] = None


class WeaningLog(BaseModel):
    approach: Literal["gradual", "partial", "abrupt_medical"] = "gradual"
    start_date: Optional[date] = None
    feeds_per_day_current: int = Field(..., ge=0, le=20)
    feeds_per_day_target: int = Field(default=0, ge=0, le=20)
    notes: Optional[str] = None


class MaternalDiscomfortLog(BaseModel):
    symptom_type: Literal[
        "mastitis", "clogged_duct", "sore_nipples", "cracked_nipples", "engorgement", "other"
    ]
    severity: int = Field(..., ge=1, le=10)
    breast_side: Optional[Literal["left", "right", "both"]] = None
    has_fever: bool = False
    temperature_c: Optional[float] = Field(default=None, ge=34, le=43)
    flu_like_symptoms: bool = False
    redness_or_hard_lump: bool = False
    log_date: Optional[date] = None
    treatment_tried: Optional[str] = None
    notes: Optional[str] = None


class InfantSensitivityLog(BaseModel):
    category: Literal["food_reaction", "allergy", "excessive_gas", "reflux", "colic", "other"]
    severity: int = Field(..., ge=1, le=10)
    suspected_trigger: Optional[str] = None
    symptoms: Optional[str] = None
    log_date: Optional[date] = None
    duration_minutes: Optional[int] = Field(default=None, ge=0)
    blood_in_stool: bool = False
    breathing_difficulty_or_swelling: bool = False
    notes: Optional[str] = None


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


class MealLog(BaseModel):
    log_date: Optional[date] = None
    meal_time: Optional[str] = None
    meal_type: Literal["breakfast", "lunch", "dinner", "snack", "other"] = "other"
    description: str = Field(..., min_length=1, max_length=1000)
    calories: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=1000)


class EHRNoteCreate(BaseModel):
    note_type: Literal["consultation", "assessment", "follow_up", "general"] = "general"
    content: str = Field(..., min_length=1, max_length=10000)


class NutritionPlanVersionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=20000)
    status: Literal["draft", "active", "archived"] = "draft"


class OfflineSyncRequest(BaseModel):
    events: List[dict] = Field(default_factory=list, max_length=100)


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
class FoodItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    calories: int = Field(..., ge=0)
    protein_g: float = Field(default=0, ge=0)
    carbs_g: float = Field(default=0, ge=0)
    fat_g: float = Field(default=0, ge=0)
    glycemic_index: Optional[int] = Field(default=None, ge=0, le=100)


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
