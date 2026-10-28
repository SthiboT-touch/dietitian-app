import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clinical_screening import screen_meal_plan_context


def test_missing_clinical_context_blocks():
    result = screen_meal_plan_context(client_id="c1", diet_type="standard", days=7)
    assert not result.ready_for_review
    assert len(result.blockers) >= 4


def test_exact_allergen_overlap_blocks():
    result = screen_meal_plan_context(client_id="c1", diet_type="standard", days=7,
        allergies=["Peanuts"], conditions=[], life_stage="adult", ingredients=["rice", "peanuts"])
    assert not result.ready_for_review
    assert any("Peanuts" in item for item in result.blockers)


def test_complete_context_only_ready_for_review():
    result = screen_meal_plan_context(client_id="c1", diet_type="standard", days=7,
        allergies=[], conditions=[], life_stage="adult", ingredients=["rice"])
    assert result.ready_for_review
    assert any("not clinical approval" in item for item in result.cautions)


def test_invalid_duration_blocks():
    result = screen_meal_plan_context(client_id="c1", diet_type="standard", days=31,
        allergies=[], conditions=[], life_stage="adult", ingredients=[])
    assert not result.ready_for_review
