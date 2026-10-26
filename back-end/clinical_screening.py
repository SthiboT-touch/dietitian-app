"""Non-diagnostic preflight checks for practitioner-authored meal plans.

This module deliberately does NOT calculate nutrition prescriptions or declare
any meal safe for a medical condition. All findings require dietitian review.
"""
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ScreeningResult:
    ready_for_review: bool
    blockers: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)


def screen_meal_plan_context(*, client_id: str, diet_type: str,
                             days: int, allergies: Iterable[str] | None = None,
                             conditions: Iterable[str] | None = None,
                             life_stage: str | None = None,
                             ingredients: Iterable[str] | None = None) -> ScreeningResult:
    """Flag missing context and exact-name ingredient/allergy overlaps.

    Exact-name overlap is NOT sufficient allergy safety screening: synonyms,
    derivatives, cross-contact and ingredient composition need human review.
    """
    blockers, cautions = [], []
    if not client_id or not client_id.strip():
        blockers.append("Client identity is required")
    if not diet_type or not diet_type.strip():
        blockers.append("Diet type is required")
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 30:
        blockers.append("Plan duration must be 1–30 days")
    if allergies is None:
        blockers.append("Allergy information must be explicitly reviewed")
    if conditions is None:
        blockers.append("Clinical conditions must be explicitly reviewed")
    if not life_stage or not life_stage.strip():
        blockers.append("Life stage must be explicitly reviewed")
    if ingredients is None:
        blockers.append("Meal ingredients must be provided for allergy screening")
    if allergies is not None and ingredients is not None:
        normalized = {str(x).strip().casefold() for x in ingredients if str(x).strip()}
        for allergen in allergies:
            if str(allergen).strip().casefold() in normalized:
                blockers.append("Potential allergen ingredient: " + str(allergen).strip())
    if conditions:
        cautions.append("Medical conditions require individualized dietitian assessment")
    cautions.append("Exact-name matching cannot establish allergy safety; check derivatives and cross-contact")
    cautions.append("Screening is not clinical approval; a dietitian must review the full plan")
    return ScreeningResult(not blockers, blockers, cautions)
