"""6. AI engine and human-in-the-loop review workflow (Llama via Ollama)."""
import json
import logging
import os
import re
import uuid
from functools import lru_cache
from fastapi import APIRouter, HTTPException
from typing import List, Optional, TypedDict
import httpx
from langchain.agents import create_agent
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from ollama import RequestError, ResponseError
import database
import config
from state import clients_db, ai_recommendations_db, ai_conversations_db, foods_db
from schemas import AIGenerateRequest, AIChatRequest, RecommendationReview
from helpers import fetch_client_profile, decode_recommendation


router = APIRouter()
logger = logging.getLogger(__name__)


# --- AI ENGINE & HUMAN-IN-THE-LOOP WORKFLOW ---

class ChatWorkflowState(TypedDict, total=False):
    user_id: str
    role: str
    message: str
    conversation: List[dict]
    reply: str
    persist: bool


class PlanWorkflowState(TypedDict, total=False):
    client_id: str
    dietary_goal: str
    client_profile: Optional[dict]
    dietitian_id: Optional[str]
    generated_plan: List[str]
    recommendation: dict


class ReviewWorkflowState(TypedDict, total=False):
    recommendation_id: str
    action: str
    notes: Optional[str]
    message: str
    recommendation: dict


def _create_chat_model(output_format: Optional[str] = None) -> ChatOllama:
    model_options = {
        "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        "keep_alive": "30m",
        "client_kwargs": {"timeout": config.OLLAMA_REQUEST_TIMEOUT_SECONDS},
    }
    if output_format is None:
        model_options["num_ctx"] = 4096
        model_options["num_predict"] = 256
    if output_format is not None:
        model_options["format"] = output_format
    return ChatOllama(**model_options)


def generate_llama_plan(dietary_goal: str, client_profile: Optional[dict] = None) -> List[str]:
    dietary_goal = (dietary_goal or "").strip()
    if not dietary_goal:
        raise HTTPException(status_code=422, detail="dietary_goal is required")

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


def _load_chat_history(state: ChatWorkflowState) -> dict:
    if "conversation" in state:
        return {"conversation": state["conversation"]}
    return {"conversation": ai_conversations_db.get(state["user_id"], [])}


def _route_chat_reply(state: ChatWorkflowState) -> str:
    return "greeting" if _greeting_reply(state["message"]) else "agent"


def _reply_to_greeting(state: ChatWorkflowState) -> dict:
    return {"reply": _greeting_reply(state["message"])}


def _reply_with_chat_agent(state: ChatWorkflowState) -> dict:
    messages = []
    for turn in state.get("conversation", [])[-8:]:
        if turn.get("role") in {"user", "assistant"} and isinstance(turn.get("content"), str):
            messages.append(
                HumanMessage(content=turn["content"])
                if turn["role"] == "user"
                else AIMessage(content=turn["content"])
            )
    messages.append(HumanMessage(content=state["message"]))

    try:
        result = _create_chat_agent(state["role"]).invoke({"messages": messages})
        content = result["messages"][-1].content
        if isinstance(content, list):
            content = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            )
        if isinstance(content, str) and content.strip():
            return {"reply": content.strip()}
    except (
        httpx.HTTPError,
        RequestError,
        ResponseError,
        OutputParserException,
        TimeoutError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
    ):
        logger.exception("LangChain AI chat request failed")
        return {
            "reply": (
                "I can't reach the AI model right now, so I don't want to guess at an answer. "
                "Please try again shortly, or ask your dietitian for guidance on a personal medical concern."
            )
        }
    return {"reply": "I couldn't get a usable answer from the AI model. Please try again shortly."}


def _persist_chat_turn(state: ChatWorkflowState) -> dict:
    conversation = [
        *state.get("conversation", []),
        {"role": "user", "content": state["message"]},
        {"role": "assistant", "content": state["reply"]},
    ]
    if state.get("persist"):
        ai_conversations_db[state["user_id"]] = conversation
    return {"conversation": conversation}


@lru_cache(maxsize=1)
def _create_chat_workflow():
    workflow = StateGraph(ChatWorkflowState)
    workflow.add_node("load_history", _load_chat_history)
    workflow.add_node("greeting_reply", _reply_to_greeting)
    workflow.add_node("agent_reply", _reply_with_chat_agent)
    workflow.add_node("persist_turn", _persist_chat_turn)
    workflow.add_edge(START, "load_history")
    workflow.add_conditional_edges(
        "load_history",
        _route_chat_reply,
        {"greeting": "greeting_reply", "agent": "agent_reply"},
    )
    workflow.add_edge("greeting_reply", "persist_turn")
    workflow.add_edge("agent_reply", "persist_turn")
    workflow.add_edge("persist_turn", END)
    return workflow.compile()


@tool
def search_food_catalog(query: str) -> str:
    """Find foods in the practice catalog by name and return their nutrition values."""
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return "No matching foods found."

    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT food_item_id AS food_id, name, calories, protein AS protein_g, "
                "carbs AS carbs_g, fat AS fat_g, glycemic_index FROM food_item "
                "WHERE LOWER(name) LIKE %s ORDER BY name LIMIT 10",
                (f"%{normalized_query}%",),
            )
            foods = [
                {
                    **dict(row),
                    "calories": round(row["calories"]),
                    "protein_g": float(row["protein_g"] or 0),
                    "carbs_g": float(row["carbs_g"] or 0),
                    "fat_g": float(row["fat_g"] or 0),
                }
                for row in cursor.fetchall()
            ]
    else:
        foods = [
            food for food in foods_db
            if normalized_query in food["name"].casefold()
        ][:10]

    return json.dumps(foods or {"message": "No matching foods found."})


@lru_cache(maxsize=2)
def _create_chat_agent(role: str):
    audience_context = (
        "The user is a client; keep guidance accessible and encourage them to discuss personal concerns with their dietitian."
        if role == "client"
        else "The user is a dietitian; provide concise support for general nutrition discussions."
    )
    system_prompt = (
        "You are an AI nutrition and exercise assistant for a dietitian and patient platform. "
        f"{audience_context} "
        "Provide practical, general guidance focused on food, hydration, meal timing, workout recovery, "
        "exercise habits, and healthy routines. Keep it brief, supportive, and actionable. "
        "Answer the latest message directly in natural language; do not return JSON or repeat the user's input. "
        "When the latest message is only a greeting or a greeting plus a social question, respond warmly and briefly "
        "to the greeting. Do not answer with details from earlier nutrition questions unless the user asks for them again. "
        "Use earlier conversation details only when they are relevant to the latest message. "
        "Use the food catalog lookup only when the user asks whether a specific item is in the practice catalog "
        "or requests its listed nutrition values. For general food ideas, answer from general knowledge without "
        "the tool. If a catalog lookup finds no match, say so briefly and do not invent catalog data. "
        "Never mention tool calls or internal tool errors. "
        "Treat catalog data as reference information, not personalized medical advice. "
        "Never diagnose a medical condition or prescribe treatment. If the user has medical concerns, "
        "encourage them to consult a licensed dietitian or healthcare professional."
    )
    return create_agent(
        model=_create_chat_model(),
        tools=[search_food_catalog],
        system_prompt=system_prompt,
    )


def _greeting_reply(message: str) -> Optional[str]:
    greeting = re.fullmatch(
        r"(?:hi|hello|hey|good morning|good afternoon|good evening)"
        r"(?:[,!.\s]+(?:how are you(?: doing)?|how's it going))?[.!?\s]*",
        message.strip(),
        flags=re.IGNORECASE,
    )
    if not greeting:
        return None
    if re.search(r"how are you|how's it going", message, flags=re.IGNORECASE):
        return "Hi! I'm here and ready to help. What nutrition or wellness question can I answer?"
    return "Hi! I'm here to help with food, hydration, meal timing, or workouts. What would you like to know?"


def generate_llama_chat_reply(message: str, role: str, conversation: Optional[List[dict]] = None) -> str:
    result = _create_chat_workflow().invoke({
        "user_id": "",
        "role": role,
        "message": message,
        "conversation": conversation or [],
        "persist": False,
    })
    return result["reply"]


def _load_plan_context(state: PlanWorkflowState) -> dict:
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            client_profile = fetch_client_profile(cursor, state["client_id"])
            cursor.execute("SELECT dietitian_id FROM client WHERE client_id = %s", (state["client_id"],))
            client_row = cursor.fetchone()
            if not client_row:
                raise HTTPException(status_code=404, detail="Client ID not found")
            dietitian_id = client_row["dietitian_id"]
    else:
        client_profile = clients_db.get(state["client_id"])
        dietitian_id = None
    return {"client_profile": client_profile, "dietitian_id": dietitian_id}


def _generate_plan_node(state: PlanWorkflowState) -> dict:
    return {
        "generated_plan": generate_llama_plan(
            state["dietary_goal"],
            state.get("client_profile"),
        )
    }


def _persist_recommendation_node(state: PlanWorkflowState) -> dict:
    recommendation_id = f"rec_{uuid.uuid4().hex[:8]}"
    recommendation = {
        "recommendation_id": recommendation_id,
        "client_id": state["client_id"],
        "dietary_goal": state["dietary_goal"],
        "status": "PENDING_REVIEW",
        "generated_plan": state["generated_plan"],
    }
    if config.DATABASE_ENABLED:
        recommendation_text = json.dumps({
            "dietary_goal": state["dietary_goal"],
            "generated_plan": state["generated_plan"],
        })
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO ai_recommendation "
                "(recommendation_id, client_id, dietitian_id, recommendation_text, status) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    recommendation_id,
                    state["client_id"],
                    state.get("dietitian_id"),
                    recommendation_text,
                    "PENDING_REVIEW",
                ),
            )
    else:
        ai_recommendations_db[recommendation_id] = recommendation
    return {"recommendation": recommendation}


@lru_cache(maxsize=1)
def _create_plan_workflow():
    workflow = StateGraph(PlanWorkflowState)
    workflow.add_node("load_client_context", _load_plan_context)
    workflow.add_node("generate_plan", _generate_plan_node)
    workflow.add_node("persist_recommendation", _persist_recommendation_node)
    workflow.add_edge(START, "load_client_context")
    workflow.add_edge("load_client_context", "generate_plan")
    workflow.add_edge("generate_plan", "persist_recommendation")
    workflow.add_edge("persist_recommendation", END)
    return workflow.compile()


def _apply_recommendation_review(state: ReviewWorkflowState) -> dict:
    recommendation_id = state["recommendation_id"]
    action = state["action"]
    notes = state.get("notes")
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "UPDATE ai_recommendation SET status = %s, client_feedback = %s "
                "WHERE recommendation_id = %s "
                "RETURNING recommendation_id, client_id, recommendation_text, client_feedback, status",
                (action, notes, recommendation_id),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Recommendation ID not found")
        recommendation = decode_recommendation(row)
    else:
        if recommendation_id not in ai_recommendations_db:
            raise HTTPException(status_code=404, detail="Recommendation ID not found")
        recommendation = ai_recommendations_db[recommendation_id]
        recommendation["status"] = action
        if notes:
            recommendation["review_notes"] = notes
    return {
        "message": f"Recommendation status updated to {action}",
        "recommendation": recommendation,
    }


@lru_cache(maxsize=1)
def _create_review_workflow():
    workflow = StateGraph(ReviewWorkflowState)
    workflow.add_node("apply_dietitian_review", _apply_recommendation_review)
    workflow.add_edge(START, "apply_dietitian_review")
    workflow.add_edge("apply_dietitian_review", END)
    return workflow.compile()


@router.post("/api/v1/ai/chat", tags=["6. AI Engine & HITL Workflow"])
def chat_with_ai(data: AIChatRequest):
    result = _create_chat_workflow().invoke({
        "user_id": data.user_id or f"{data.role}-chat",
        "role": data.role,
        "message": data.message,
        "persist": True,
    })
    return {"reply": result["reply"], "messages": result["conversation"]}


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
    result = _create_plan_workflow().invoke({
        "client_id": data.client_id,
        "dietary_goal": data.dietary_goal,
    })
    return {"message": "AI recommendation drafted", "recommendation": result["recommendation"]}

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
    return _create_review_workflow().invoke({
        "recommendation_id": recommendation_id,
        "action": data.action,
        "notes": data.notes,
    })
