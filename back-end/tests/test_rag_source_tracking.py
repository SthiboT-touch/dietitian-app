import json
from helpers import decode_recommendation

def test_decode_recommendation_keeps_sources():
    row = {"recommendation_id":"r1", "client_id":"c1", "recommendation_text":json.dumps({"dietary_goal":"balanced meals", "generated_plan":["Example"], "retrieved_references":[{"source":"reviewed.txt", "paragraph":2, "excerpt":"Reference text"}]}), "status":"PENDING_REVIEW", "client_feedback":None}
    result = decode_recommendation(row)
    assert result["retrieved_references"][0]["source"] == "reviewed.txt"
