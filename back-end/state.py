"""In-memory stores used when no DATABASE_URL is configured (development and tests)."""
from typing import Dict, List


users_db: Dict[str, dict] = {}
admins_db: Dict[str, dict] = {}
businesses_db: Dict[str, dict] = {}
branches_db: Dict[str, dict] = {}
admin_sessions_db: Dict[str, str] = {}
dietitian_sessions_db: Dict[str, str] = {}
dietitian_documents_db: Dict[str, dict] = {}
approval_log_db: List[dict] = []
clients_db: Dict[str, dict] = {}
appointments_db: Dict[str, dict] = {}
goals_db: Dict[str, List[dict]] = {}
meal_plans_db: Dict[str, dict] = {}
recipes_db: Dict[str, dict] = {}
ai_recommendations_db: Dict[str, dict] = {}
ai_conversations_db: Dict[str, List[dict]] = {}
foods_db: List[dict] = [
    {"food_id": "f1", "name": "Oatmeal", "calories": 150, "protein_g": 5.0, "carbs_g": 27.0, "fat_g": 3.0, "glycemic_index": 55},
    {"food_id": "f2", "name": "Grilled Chicken Breast", "calories": 165, "protein_g": 31.0, "carbs_g": 0.0, "fat_g": 3.6, "glycemic_index": 0}
]
