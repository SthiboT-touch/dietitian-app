"""Lactation guidance content and safety checks used by routers/clients.py."""

INCREASE_MILK_GUIDANCE = {
    "title": "Increasing milk production",
    "principles": [
        "Remove milk often: aim for 8-12 breastfeeding or pumping sessions per 24 hours, including night feeds in the early months.",
        "Check latch and milk transfer with a lactation consultant if the baby feeds for a long time without swallowing.",
        "Offer both breasts at each feed and use breast compression to help milk transfer.",
        "Add a pumping session after feeds, or power-pump for 20-30 minutes, to signal higher demand.",
        "Skin-to-skin contact supports let-down.",
    ],
    "nutrition": [
        "Lactation needs roughly 330-400 extra kcal per day on average; do not crash diet.",
        "Eat regular meals and snacks with protein, whole grains, healthy fats, fruit and vegetables.",
        "Drink to thirst and keep water within reach during feeds.",
        "Include iron, iodine, choline, vitamin B12, calcium and omega-3 (DHA) foods, and continue postnatal supplements as advised.",
        "Oats, fenugreek and other galactagogues have limited evidence - check with a clinician before using supplements or herbs.",
    ],
    "seek_help_if": [
        "Fewer than 6 wet diapers a day after day 5, a lethargic baby, or poor weight gain.",
        "Supply drops suddenly, or there is persistent breast pain or fever.",
        "Thyroid problems, PCOS, diabetes or previous breast surgery may be affecting supply.",
    ],
}

OVERSUPPLY_GUIDANCE = {
    "title": "Managing over-supply",
    "principles": [
        "Block feeding: offer one breast for a set block (for example 2-3 hours) before switching sides.",
        "Feed before the baby is frantic and use a reclined position to slow the flow.",
        "Pump or hand-express only enough to relieve discomfort - emptying the breast signals more production.",
        "Burp often; watch for gulping, clicking, green frothy stools or gassiness (possible fast flow).",
        "Do not stop abruptly or restrict fluids sharply - this raises the risk of clogged ducts and mastitis.",
    ],
    "nutrition": [
        "Keep a balanced diet and eat to hunger; there is no need to cut calories or fluids sharply.",
        "Drink to thirst rather than forcing fluids.",
        "Sage and peppermint are folk remedies with limited evidence; check with your clinician first.",
    ],
    "seek_help_if": [
        "A hard, red, painful area, flu-like symptoms or fever (possible mastitis).",
        "The baby is not gaining weight well despite abundant supply.",
        "Medication to reduce supply is being considered - this needs medical supervision.",
    ],
}


def weaning_guidance(current_sessions: int = 6, target_sessions: int = 0, approach: str = "gradual"):
    sessions_to_drop = max(current_sessions - target_sessions, 0)
    pace = "Follow your prescriber's plan" if approach == "abrupt_medical" else "Drop one feed or pump session every 3-7 days"
    return {
        "title": "Weaning nutrition: safely lowering milk production",
        "plan": {
            "current_sessions_per_day": current_sessions,
            "target_sessions_per_day": target_sessions,
            "sessions_to_drop": sessions_to_drop,
            "suggested_pace": pace,
            "estimated_weeks": max(round(sessions_to_drop * 0.7), 1) if sessions_to_drop else 0,
        },
        "tips": [
            "Drop the session the baby cares least about first; keep early-morning and bedtime feeds for last.",
            "Replace dropped breastfeeds with formula, cup or solids as age-appropriate (infants under 12 months need breast milk or formula as their main milk).",
            "Gradual weaning lowers the risk of engorgement, clogged ducts and mastitis.",
            "Express only enough to relieve fullness, not to empty the breast.",
        ],
        "nutrition": [
            "Lower the extra ~330-400 kcal gradually as production falls, based on hunger and weight - not restriction.",
            "Do not cut fluids sharply; drink to thirst.",
            "Keep protein, calcium (about 1000 mg/day), iron, iodine and vitamin D adequate.",
            "Include fibre-rich foods, fruit and vegetables; limit alcohol and ultra-processed foods.",
            "Sage, peppermint and cabbage leaves are traditional remedies with limited evidence; cold compresses and a supportive bra help comfort.",
        ],
        "avoid": [
            "Abrupt stopping without medical advice, tight breast binding, or severe fluid or calorie restriction.",
            "Medications or herbal products to dry up milk without a clinician.",
        ],
        "warning_signs": [
            "Hard, hot, red or very painful breast, fever of 38.5 C or higher, or flu-like symptoms - possible mastitis, seek care promptly.",
            "Persistent low mood or anxiety - speak to your healthcare provider.",
        ],
    }


DISCOMFORT_SELF_CARE = {
    "mastitis": ["Keep feeding or expressing from the affected breast; do not stop abruptly.", "Rest, drink fluids and wear a supportive bra.", "Use gentle massage (not deep pressure) and cool compresses after feeds."],
    "clogged_duct": ["Feed often, starting on the affected side.", "Use warmth before feeds, gentle massage toward the nipple, and a cool compress after.", "Check bra fit and latch position."],
    "sore_nipples": ["Check latch and positioning with a lactation consultant.", "Express a little milk onto the nipple and air dry after feeds.", "Lanolin or hydrogel pads may help if comfortable."],
    "cracked_nipples": ["Correct latch and positioning; use a nipple shield only with guidance.", "Keep the area clean and use moist-healing (lanolin or hydrogel).", "Seek care if it looks infected (pus, spreading redness) or is not healing."],
    "engorgement": ["Feed or express often to soften the breast.", "Use cold packs between feeds and brief warmth before feeds.", "Reverse-pressure softening around the areola can help the baby latch."],
    "other": ["Track the pattern and discuss it with your healthcare provider."],
}


def discomfort_red_flags(data):
    flags = []
    if (data.temperature_c is not None and data.temperature_c >= 38.5) or data.has_fever:
        flags.append("Fever (38.5 C or higher).")
    if data.flu_like_symptoms:
        flags.append("Flu-like symptoms (aches, chills, fatigue).")
    if data.symptom_type in ("mastitis", "clogged_duct") and data.redness_or_hard_lump and data.severity >= 7:
        flags.append("Severe, red or hard painful area.")
    return flags


def infant_red_flags(data):
    flags = []
    if data.breathing_difficulty_or_swelling:
        flags.append("Breathing difficulty or face/lip swelling - call emergency services immediately.")
    if data.blood_in_stool:
        flags.append("Blood in the stool - contact the baby's paediatrician promptly.")
    if data.category == "allergy" and data.severity >= 7:
        flags.append("Severe allergic reaction - seek urgent medical care.")
    return flags


def daily_feeding_observations(entry):
    notes = []
    if entry.get("wet_diapers") is not None and entry["wet_diapers"] < 6:
        notes.append("Fewer than 6 wet diapers in 24 hours may signal low intake - contact a healthcare provider.")
    sessions = (entry.get("breastfeeding_sessions") or 0) + (entry.get("pumping_sessions") or 0)
    if sessions < 8 and not entry.get("formula_feeds"):
        notes.append("Fewer than about 8 milk-removal sessions in 24 hours may reduce supply in young infants.")
    return notes
