"""6. AI engine and human-in-the-loop review workflow (Llama via Ollama)."""
import json
import logging
import os
import re
import uuid
from functools import lru_cache
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional, TypedDict
import httpx
import psycopg2
from langchain.agents import create_agent
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from ollama import RequestError, ResponseError
import database
import config
import tracing
from security import Principal, require_dietitian, require_session
from access import require_client_access
from state import clients_db, ai_recommendations_db, ai_conversations_db, foods_db, recommendation_run_ids
from schemas import AIGenerateRequest, AIChatRequest, RecommendationReview
from helpers import fetch_client_profile, decode_recommendation


router = APIRouter()
logger = logging.getLogger(__name__)

# Small models sometimes write a tool call as plain text instead of making it; never show that to users.
TOOL_CALL_TEXT = re.compile(r'\s*\{\s*"name"\s*:\s*"[^"]*"\s*,\s*"(?:parameters|arguments)')
CATALOG_QUESTION = re.compile(r"\bcatalog(?:ue)?s?\b|\blisted\b|\bin stock\b", re.IGNORECASE)
# Long prompts are slow to read on a CPU, so the agent sees only the latest exchanges.
CHAT_HISTORY_MESSAGES = 4

# Errors that mean "the model is unreachable or answered badly". ConnectionError is what the
# ollama client raises when the server is down, and it is not an httpx error.
PLAN_MODEL_ERRORS = (
    httpx.HTTPError,
    RequestError,
    ResponseError,
    OutputParserException,
    ConnectionError,
    TimeoutError,
    TypeError,
    ValueError,
)
CHAT_MODEL_ERRORS = (*PLAN_MODEL_ERRORS, GraphRecursionError, IndexError, KeyError)


# --- AI ENGINE & HUMAN-IN-THE-LOOP WORKFLOW ---

class ChatWorkflowState(TypedDict, total=False):
    user_id: str
    user_name: Optional[str]
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
    run_id: str
    recommendation: dict


class ReviewWorkflowState(TypedDict, total=False):
    recommendation_id: str
    action: str
    notes: Optional[str]
    message: str
    recommendation: dict
    trace_run_id: Optional[str]


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
    except PLAN_MODEL_ERRORS as exc:
        logger.warning("Plan generation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Llama service unavailable or returned an invalid response. Check Ollama and the configured model.",
        ) from exc


def _allergen_stem(name: str) -> str:
    """Lower-case an allergen and drop a plural 's' so 'peanuts' also catches 'peanut butter'."""
    stem = (name or "").strip().casefold()
    return stem[:-1] if len(stem) > 3 and stem.endswith("s") else stem


def generate_llama_meal_plan(diet_type: str, days: int, client_profile: Optional[dict] = None) -> dict:
    """Ask the model for one representative day of meals plus a grocery list for the whole plan."""
    profile = client_profile or {}
    allergies = profile.get("allergies", [])
    context = {
        "diet_type": (diet_type or "").strip(),
        "days": days,
        "allergies": allergies,
        "medical_conditions": profile.get("conditions", []),
    }
    try:
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "Draft a general meal plan for review by a licensed dietitian. "
                "Never include any listed allergen or a food that contains it. "
                "Do not diagnose or claim the plan treats a medical condition. "
                "Reply with a JSON object with two arrays of plain strings. "
                "'meals' has 3 to 6 short items for one representative day, for example "
                "'Breakfast: oatmeal with berries'. 'grocery_list' has 5 to 20 short ingredient "
                "names to buy for the whole plan, one item per string, with no quantities and no nested objects.",
            ),
            ("human", "{context}"),
        ])
        chain = prompt | _create_chat_model(output_format="json") | JsonOutputParser()
        generated = chain.invoke(
            {"context": json.dumps(context)},
            config=tracing.trace_config("generate_meal_plan", tags=("meal-plan",)),
        )
        if not isinstance(generated, dict):
            raise ValueError("The model returned an invalid meal plan")
        meals = generated.get("meals")
        grocery = generated.get("grocery_list")
        for items in (meals, grocery):
            if not isinstance(items, list) or not items or not all(isinstance(item, str) and item.strip() for item in items):
                raise ValueError("The model returned an invalid meal plan")
    except PLAN_MODEL_ERRORS as exc:
        logger.warning("Meal plan generation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Llama service unavailable or returned an invalid response. Check Ollama and the configured model.",
        ) from exc

    # Safety net: never save a draft that mentions a recorded allergen, whatever the model says.
    allergen_stems = [
        _allergen_stem(item.get("allergen", "")) for item in allergies if isinstance(item, dict)
    ]
    text = " ".join([*meals, *grocery]).casefold()
    if any(stem and stem in text for stem in allergen_stems):
        raise HTTPException(
            status_code=422,
            detail="The AI draft mentioned an ingredient that matches this patient's recorded allergies. Please generate it again.",
        )
    return {"meals": [item.strip() for item in meals], "grocery_list": [item.strip() for item in grocery]}


def _load_chat_history(state: ChatWorkflowState) -> dict:
    if "conversation" in state:
        return {"conversation": state["conversation"]}
    return {"conversation": ai_conversations_db.get(state["user_id"], [])}


def _route_chat_reply(state: ChatWorkflowState) -> str:
    if _greeting_reply(state["message"]) or _name_reply(state["message"], state.get("user_name")):
        return "greeting"
    return "agent"


def _reply_to_greeting(state: ChatWorkflowState) -> dict:
    return {"reply": _greeting_reply(state["message"]) or _name_reply(state["message"], state.get("user_name"))}


def _reply_with_chat_agent(state: ChatWorkflowState) -> dict:
    user_name = (state.get("user_name") or "").strip()
    messages = [SystemMessage(content=(
        f"The user's name is {user_name}. If they ask for their name, tell them it is {user_name}." if user_name
        else "You do not know the user's name. If they ask for it, say you don't know it and invite them to share it. "
        "Never search the food catalog for a person's name."
    ))]
    for turn in state.get("conversation", [])[-CHAT_HISTORY_MESSAGES:]:
        if turn.get("role") in {"user", "assistant"} and isinstance(turn.get("content"), str):
            messages.append(
                HumanMessage(content=turn["content"])
                if turn["role"] == "user"
                else AIMessage(content=turn["content"])
            )
    messages.append(HumanMessage(content=state["message"]))

    try:
        agent = _create_chat_agent(state["role"], _asks_about_catalog(state["message"]))
        # Model -> tool -> model is enough; stop loops before they outlast the proxy timeout.
        result = agent.invoke({"messages": messages}, config={"recursion_limit": 6})
        content = result["messages"][-1].content
        if isinstance(content, list):
            content = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            )
        if isinstance(content, str) and content.strip() and not TOOL_CALL_TEXT.match(content):
            return {"reply": content.strip()}
    except CHAT_MODEL_ERRORS:
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
        try:
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
        except psycopg2.Error:
            logger.exception("Food catalog lookup failed")
            return "The food catalog is unavailable right now. Answer from general knowledge without catalog data."
    else:
        foods = [
            food for food in foods_db
            if normalized_query in food["name"].casefold()
        ][:10]

    return json.dumps(foods or {"message": "No matching foods found."})


def _asks_about_catalog(message: str) -> bool:
    return bool(CATALOG_QUESTION.search(message))


@lru_cache(maxsize=4)
def _create_chat_agent(role: str, use_catalog: bool = False):
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
        "Never diagnose a medical condition or prescribe treatment. If the user has medical concerns, "
        "encourage them to consult a licensed dietitian or healthcare professional. "
    )
    if use_catalog:
        system_prompt += (
            "Use the food catalog lookup to answer questions about items in the practice catalog or their listed "
            "nutrition values. If a catalog lookup finds no match, say so briefly and do not invent catalog data. "
            "Your only tool is the food catalog lookup; never invent other tools or write tool calls as text. "
            "Never mention tool calls or internal tool errors. "
            "Treat catalog data as reference information, not personalized medical advice."
        )
    else:
        system_prompt += "You have no tools; answer from general knowledge and never write tool calls or JSON."
    # Only offer the tool when it is needed: every tool round trip is another slow model call on a CPU server.
    return create_agent(
        model=_create_chat_model(),
        tools=[search_food_catalog] if use_catalog else [],
        system_prompt=system_prompt,
    )


def _name_reply(message: str, user_name: Optional[str]) -> Optional[str]:
    asks_name = re.fullmatch(
        r"(?:(?:hi|hello|hey)[,!.\s]+)?(?:what(?:'s| is|s) my name|do you know my name|who am i)[.!?\s]*",
        message.strip(),
        flags=re.IGNORECASE,
    )
    if not asks_name:
        return None
    user_name = (user_name or "").strip()
    if user_name:
        return f"Your name is {user_name}. How can I help with your nutrition or wellness today?"
    return "I don't know your name yet. Feel free to share it, and tell me what nutrition or wellness question I can help with."


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


def generate_llama_chat_reply(
    message: str, role: str, conversation: Optional[List[dict]] = None, user_name: Optional[str] = None
) -> str:
    result = _create_chat_workflow().invoke({
        "user_id": "",
        "user_name": user_name,
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
            "trace_run_id": state.get("run_id"),
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
        if state.get("run_id"):
            recommendation_run_ids[recommendation_id] = state["run_id"]
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
        try:
            trace_run_id = json.loads(row["recommendation_text"]).get("trace_run_id")
        except (TypeError, ValueError, AttributeError):
            trace_run_id = None
    else:
        if recommendation_id not in ai_recommendations_db:
            raise HTTPException(status_code=404, detail="Recommendation ID not found")
        recommendation = ai_recommendations_db[recommendation_id]
        recommendation["status"] = action
        if notes:
            recommendation["review_notes"] = notes
        trace_run_id = recommendation_run_ids.get(recommendation_id)
    return {
        "message": f"Recommendation status updated to {action}",
        "recommendation": recommendation,
        "trace_run_id": trace_run_id,
    }


@lru_cache(maxsize=1)
def _create_review_workflow():
    workflow = StateGraph(ReviewWorkflowState)
    workflow.add_node("apply_dietitian_review", _apply_recommendation_review)
    workflow.add_edge(START, "apply_dietitian_review")
    workflow.add_edge("apply_dietitian_review", END)
    return workflow.compile()


@router.post("/api/v1/ai/chat", tags=["6. AI Engine & HITL Workflow"])
def chat_with_ai(data: AIChatRequest, principal: Principal = Depends(require_session)):
    if principal.role != "admin" and (data.user_id != principal.id or data.role != principal.role):
        raise HTTPException(status_code=403, detail="You can only use your own AI chat")
    user_id = data.user_id or f"{data.role}-chat"
    result = _create_chat_workflow().invoke(
        {
            "user_id": user_id,
            "user_name": data.user_name,
            "role": data.role,
            "message": data.message,
            "persist": True,
        },
        config=tracing.trace_config(
            "ai_chat",
            tags=("chat", data.role),
            metadata={"thread_id": user_id, "role": data.role},  # groups a conversation in LangSmith Threads
        ),
    )
    return {"reply": result["reply"], "messages": result["conversation"]}


@router.get("/api/v1/ai/chat", tags=["6. AI Engine & HITL Workflow"])
def get_ai_chat(user_id: str, role: str = "client", principal: Principal = Depends(require_session)):
    if principal.role != "admin" and user_id != principal.id:
        raise HTTPException(status_code=403, detail="You can only view your own AI chat")
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
def trigger_ai_plan(data: AIGenerateRequest, dietitian_id: str = Depends(require_dietitian)):
    run_id = uuid.uuid4()
    result = _create_plan_workflow().invoke(
        {
            "client_id": data.client_id,
            "dietary_goal": data.dietary_goal,
            "run_id": str(run_id),
        },
        config=tracing.trace_config("generate_plan", tags=("plan",), run_id=run_id),
    )
    return {"message": "AI recommendation drafted", "recommendation": result["recommendation"]}

@router.get("/api/v1/ai/recommendations/pending", tags=["6. AI Engine & HITL Workflow"])
def get_pending_recommendations(dietitian_id: str = Depends(require_dietitian)):
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
def get_client_recommendations(client_id: str, principal: Principal = Depends(require_session)):
    require_client_access(principal, client_id)
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
def review_ai_recommendation(
    recommendation_id: str,
    data: RecommendationReview,
    dietitian_id: str = Depends(require_dietitian),
):
    result = dict(_create_review_workflow().invoke(
        {
            "recommendation_id": recommendation_id,
            "action": data.action,
            "notes": data.notes,
        },
        config=tracing.trace_config("review_recommendation", tags=("review",), metadata={"action": data.action}),
    ))
    # Attach the dietitian's decision to the trace that drafted the plan (never raises).
    tracing.record_review_feedback(result.pop("trace_run_id", None), data.action)
    return result
