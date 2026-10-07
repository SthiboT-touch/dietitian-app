"""6. AI engine and human-in-the-loop review workflow (Llama via Ollama)."""
import json
import os
import uuid
from fastapi import APIRouter, HTTPException
from typing import List, Optional
import httpx
from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from ollama import RequestError, ResponseError
import database
import config
from state import clients_db, ai_recommendations_db, ai_conversations_db
from schemas import AIGenerateRequest, AIChatRequest, RecommendationReview
from helpers import fetch_client_profile, decode_recommendation


router = APIRouter()


# --- AI ENGINE & HUMAN-IN-THE-LOOP WORKFLOW ---

def _create_chat_model(output_format: Optional[str] = None) -> ChatOllama:
    model_options = {
        "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        "keep_alive": "30m",
        "client_kwargs": {"timeout": config.OLLAMA_REQUEST_TIMEOUT_SECONDS},
    }
    if output_format is not None:
        model_options["format"] = output_format
    return ChatOllama(**model_options)


def generate_llama_plan(dietary_goal: str, client_profile: Optional[dict] = None) -> List[str]:
    profile = client_profile or {}
    context = {
        "dietary_goal": dietary_goal,
        "allergies": profile.get("allergies", []),
        "medical_conditions": profile.get("conditions", []),
    }
    try:
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "Draft a short, general nutrition plan for review by a licensed dietitian. "
                "Respect all listed allergies. Do not diagnose, prescribe treatment, "
                "or make claims that the plan treats a medical condition. "
                "Reply with a JSON object containing a 'plan' array of 3 to 5 short "
                "plain-text suggestions, one sentence each (e.g. 'Breakfast: oatmeal "
                "with berries'). Do not nest days, meals, or objects inside the list; "
                "each list item must be a single short string.",
            ),
            ("human", "{context}"),
        ])
        chain = prompt | _create_chat_model(output_format="json") | JsonOutputParser()
        generated = chain.invoke({"context": json.dumps(context)})
        if not isinstance(generated, dict):
            raise ValueError("The model returned an invalid plan")
        plan = generated.get("plan")
        if not isinstance(plan, list) or not plan or not all(isinstance(item, str) for item in plan):
            raise ValueError("The model returned an invalid plan")
        return plan
    except (
        httpx.HTTPError,
        RequestError,
        ResponseError,
        OutputParserException,
        TimeoutError,
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail="Llama service unavailable or returned an invalid response. Check Ollama and the configured model.",
        ) from exc


def generate_llama_chat_reply(message: str, role: str, conversation: Optional[List[dict]] = None) -> str:
    system_prompt = (
        "You are an AI nutrition and exercise assistant for a dietitian and patient platform. "
        "Provide practical, general guidance focused on food, hydration, meal timing, workout recovery, "
        "exercise habits, and healthy routines. Keep it brief, supportive, and actionable. "
        "Answer the latest message directly in natural language; do not return JSON or repeat the user's input. "
        "Never diagnose a medical condition or prescribe treatment. If the user has medical concerns, "
        "encourage them to consult a licensed dietitian or healthcare professional."
    )
    messages = [("system", system_prompt)]
    for turn in (conversation or [])[-8:]:
        if turn.get("role") in {"user", "assistant"} and isinstance(turn.get("content"), str):
            messages.append((turn["role"], turn["content"]))
    messages.append(("human", "{message}"))

    try:
        prompt = ChatPromptTemplate.from_messages(messages)
        chain = prompt | _create_chat_model() | StrOutputParser()
        content = chain.invoke({"message": message})
        if isinstance(content, str) and content.strip():
            return content.strip()
    except (httpx.HTTPError, RequestError, ResponseError, TimeoutError, TypeError, ValueError):
        return (
            "I can't reach the AI model right now, so I don't want to guess at an answer. "
            "Please try again shortly, or ask your dietitian for guidance on a personal medical concern."
        )
    return "I couldn't get a usable answer from the AI model. Please try again shortly."


@router.post("/api/v1/ai/chat", tags=["6. AI Engine & HITL Workflow"])
def chat_with_ai(data: AIChatRequest):
    conversation_key = data.user_id or f"{data.role}-chat"
    conversation = ai_conversations_db.setdefault(conversation_key, [])
    reply = generate_llama_chat_reply(data.message, data.role, conversation)
    user_message = {"role": "user", "content": data.message}
    assistant_message = {"role": "assistant", "content": reply}
    conversation.extend([user_message, assistant_message])
    return {"reply": reply, "messages": conversation}


@router.get("/api/v1/ai/chat", tags=["6. AI Engine & HITL Workflow"])
def get_ai_chat(user_id: str, role: str = "client"):
    key = user_id or f"{role}-chat"
    messages = ai_conversations_db.get(key, [])
    if not messages:
        initial_message = {
            "role": "assistant",
            "content": "Ask me about food, workouts, hydration, meal timing, or healthy habits for your plan.",
        }
        messages = [initial_message]
        ai_conversations_db[key] = messages
    return {"messages": messages}


@router.post("/api/v1/ai/generate-plan", tags=["6. AI Engine & HITL Workflow"])
def trigger_ai_plan(data: AIGenerateRequest):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            client_profile = fetch_client_profile(cursor, data.client_id)
            cursor.execute("SELECT dietitian_id FROM client WHERE client_id = %s", (data.client_id,))
            dietitian_id = cursor.fetchone()["dietitian_id"]
    else:
        client_profile = clients_db.get(data.client_id)
        dietitian_id = None
    generated_plan = generate_llama_plan(data.dietary_goal, client_profile)
    rec_id = f"rec_{uuid.uuid4().hex[:8]}"
    rec_data = {
        "recommendation_id": rec_id,
        "client_id": data.client_id,
        "dietary_goal": data.dietary_goal,
        "status": "PENDING_REVIEW",
        "generated_plan": generated_plan
    }
    if config.DATABASE_ENABLED:
        recommendation_text = json.dumps({
            "dietary_goal": data.dietary_goal,
            "generated_plan": generated_plan,
        })
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO ai_recommendation "
                "(recommendation_id, client_id, dietitian_id, recommendation_text, status) "
                "VALUES (%s, %s, %s, %s, %s)",
                (rec_id, data.client_id, dietitian_id, recommendation_text, "PENDING_REVIEW"),
            )
    else:
        ai_recommendations_db[rec_id] = rec_data
    return {"message": "AI recommendation drafted", "recommendation": rec_data}

@router.get("/api/v1/ai/recommendations/pending", tags=["6. AI Engine & HITL Workflow"])
def get_pending_recommendations():
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT recommendation_id, client_id, recommendation_text, client_feedback, status "
                "FROM ai_recommendation WHERE status = 'PENDING_REVIEW' ORDER BY generated_date"
            )
            return [decode_recommendation(row) for row in cursor.fetchall()]
    pending = [r for r in ai_recommendations_db.values() if r["status"] == "PENDING_REVIEW"]
    return pending


@router.get("/api/v1/ai/recommendations", tags=["6. AI Engine & HITL Workflow"])
def get_client_recommendations(client_id: str):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT recommendation_id, client_id, recommendation_text, client_feedback, status "
                "FROM ai_recommendation WHERE client_id = %s AND status IN ('APPROVED', 'MODIFIED') "
                "ORDER BY generated_date DESC",
                (client_id,),
            )
            return [decode_recommendation(row) for row in cursor.fetchall()]
    return [
        recommendation for recommendation in ai_recommendations_db.values()
        if recommendation.get("client_id") == client_id
        and recommendation.get("status") in {"APPROVED", "MODIFIED"}
    ]

@router.patch("/api/v1/ai/recommendations/{recommendation_id}", tags=["6. AI Engine & HITL Workflow"])
def review_ai_recommendation(recommendation_id: str, data: RecommendationReview):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "UPDATE ai_recommendation SET status = %s, client_feedback = %s "
                "WHERE recommendation_id = %s "
                "RETURNING recommendation_id, client_id, recommendation_text, client_feedback, status",
                (data.action, data.notes, recommendation_id),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Recommendation ID not found")
        recommendation = decode_recommendation(row)
        return {
            "message": f"Recommendation status updated to {data.action}",
            "recommendation": recommendation,
        }
    if recommendation_id not in ai_recommendations_db:
        raise HTTPException(status_code=404, detail="Recommendation ID not found")
    ai_recommendations_db[recommendation_id]["status"] = data.action
    if data.notes:
        ai_recommendations_db[recommendation_id]["review_notes"] = data.notes
    return {"message": f"Recommendation status updated to {data.action}", "recommendation": ai_recommendations_db[recommendation_id]}
